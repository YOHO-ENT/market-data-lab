import { Copy, Plus, Trash2, Users } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  addUniverseTicker,
  deleteUniverseTicker,
  getUniverses,
} from "../api/marketApi";
import type { UniverseGroup } from "../model/types";

type LoadPhase = "idle" | "loading" | "ready" | "error";

export function UniversesPage() {
  const [groups, setGroups] = useState<UniverseGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [ticker, setTicker] = useState("");
  const [phase, setPhase] = useState<LoadPhase>("idle");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === selectedGroupId) || groups[0] || null,
    [groups, selectedGroupId],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadGroups() {
      setPhase("loading");
      setError(null);
      const response = await getUniverses();
      if (cancelled) {
        return;
      }
      setGroups(response);
      setSelectedGroupId((current) =>
        response.some((group) => group.id === current) ? current : response[0]?.id || "",
      );
      setPhase("ready");
    }

    loadGroups().catch((loadError) => {
      if (!cancelled) {
        setError(loadError instanceof Error ? loadError.message : String(loadError));
        setGroups([]);
        setPhase("error");
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  async function reloadGroups(nextMessage?: string) {
    const response = await getUniverses();
    setGroups(response);
    setSelectedGroupId((current) =>
      response.some((group) => group.id === current) ? current : response[0]?.id || "",
    );
    if (nextMessage) {
      setMessage(nextMessage);
    }
  }

  async function handleAddTicker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedGroup) {
      return;
    }
    const normalizedTicker = ticker.trim().toUpperCase();
    if (!normalizedTicker) {
      setError("Enter a ticker before adding it to a universe.");
      return;
    }

    setBusyKey(`add:${selectedGroup.id}`);
    setError(null);
    setMessage(null);
    try {
      await addUniverseTicker(selectedGroup.id, normalizedTicker);
      setTicker("");
      await reloadGroups(`${normalizedTicker} added to ${selectedGroup.name}.`);
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : String(mutationError));
    } finally {
      setBusyKey(null);
    }
  }

  async function handleDeleteTicker(group: UniverseGroup, tickerToDelete: string) {
    setBusyKey(`delete:${group.id}:${tickerToDelete}`);
    setError(null);
    setMessage(null);
    try {
      await deleteUniverseTicker(group.id, tickerToDelete);
      await reloadGroups(`${tickerToDelete} removed from ${group.name}.`);
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : String(mutationError));
    } finally {
      setBusyKey(null);
    }
  }

  async function handleCopy(group: UniverseGroup) {
    const tickerList = group.tickers.join(", ");
    try {
      await navigator.clipboard.writeText(tickerList);
      setMessage(`${group.name} ticker list copied.`);
      setError(null);
    } catch (copyError) {
      setError(copyError instanceof Error ? copyError.message : String(copyError));
    }
  }

  const totalTickers = groups.reduce((total, group) => total + group.tickers.length, 0);

  return (
    <div className="market-page">
      <section className="screen-header section-card">
        <div>
          <div className="eyebrow">Universes</div>
          <h1>Configured ticker groups</h1>
          <p>Add, remove, and copy local universe members without starting a data refresh.</p>
        </div>
        <div className="screen-header-meta">
          <Users size={16} aria-hidden="true" />
          <span className="mono">
            {groups.length} groups / {totalTickers} tickers
          </span>
        </div>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}
      {message ? <div className="success-banner">{message}</div> : null}

      <section className="universe-manager section-card">
        <form className="universe-add-form" onSubmit={handleAddTicker}>
          <label className="control-field">
            <span className="control-label">Group</span>
            <select
              aria-label="Universe group"
              value={selectedGroup?.id || ""}
              onChange={(event) => setSelectedGroupId(event.target.value)}
              disabled={phase === "loading" || groups.length === 0}
            >
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </select>
          </label>
          <label className="control-field">
            <span className="control-label">Ticker</span>
            <input
              aria-label="Ticker to add"
              value={ticker}
              onChange={(event) => setTicker(event.target.value.toUpperCase())}
              placeholder="AAPL"
              disabled={!selectedGroup || busyKey !== null}
            />
          </label>
          <button
            type="submit"
            className="primary-action-button"
            disabled={!selectedGroup || busyKey !== null}
          >
            <Plus size={15} aria-hidden="true" />
            Add ticker
          </button>
        </form>

        <div className="universe-grid">
          {phase === "loading" || phase === "idle" ? (
            <div className="table-empty">Loading universes...</div>
          ) : groups.length > 0 ? (
            groups.map((group) => (
              <UniverseGroupCard
                key={group.id}
                group={group}
                busyKey={busyKey}
                onCopy={() => handleCopy(group)}
                onDelete={(tickerToDelete) => handleDeleteTicker(group, tickerToDelete)}
              />
            ))
          ) : (
            <div className="table-empty">No universe groups are configured.</div>
          )}
        </div>
      </section>
    </div>
  );
}

function UniverseGroupCard({
  group,
  busyKey,
  onCopy,
  onDelete,
}: {
  group: UniverseGroup;
  busyKey: string | null;
  onCopy: () => void;
  onDelete: (ticker: string) => void;
}) {
  return (
    <article className="universe-card">
      <div className="universe-card-header">
        <div>
          <h2>{group.name}</h2>
          {group.description ? <p>{group.description}</p> : null}
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label={`Copy ${group.name} tickers`}
          title={`Copy ${group.name} tickers`}
          onClick={onCopy}
        >
          <Copy size={16} aria-hidden="true" />
        </button>
      </div>
      <div className="universe-card-meta">
        <span className="mono">{group.tickers.length} tickers</span>
        {group.updated_at ? <span>Updated {group.updated_at}</span> : null}
        {group.source ? <span>{group.source}</span> : null}
      </div>
      <div className="universe-ticker-list">
        {group.tickers.map((ticker) => (
          <div className="universe-ticker-row" key={ticker}>
            <Link className="ticker-link mono" to={`/market/${encodeURIComponent(ticker)}`}>
              {ticker}
            </Link>
            <button
              type="button"
              className="icon-button danger-button"
              aria-label={`Delete ${ticker} from ${group.name}`}
              title={`Delete ${ticker} from ${group.name}`}
              disabled={busyKey === `delete:${group.id}:${ticker}`}
              onClick={() => onDelete(ticker)}
            >
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </article>
  );
}
