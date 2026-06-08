import { Copy, FolderPlus, Plus, Users } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  addUniverseTicker,
  deleteUniverseGroup,
  deleteUniverseTicker,
  getUniverseConfig,
  replaceUniverseGroup,
} from "../api/marketApi";
import type { UniverseGroup } from "../model/types";

type LoadPhase = "idle" | "loading" | "ready" | "error";

export function UniversesPage() {
  const [groups, setGroups] = useState<UniverseGroup[]>([]);
  const [newGroupName, setNewGroupName] = useState("");
  const [tickerInputs, setTickerInputs] = useState<Record<string, string>>({});
  const [phase, setPhase] = useState<LoadPhase>("idle");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [managedMessage, setManagedMessage] = useState("Managed by Moomoo. Run moomoo-sync to update.");
  const [editable, setEditable] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadGroups() {
      setPhase("loading");
      setError(null);
      const response = await getUniverseConfig();
      if (cancelled) {
        return;
      }
      setGroups(response.groups);
      setEditable(response.editable);
      setManagedMessage(response.message || "Managed by Moomoo. Run moomoo-sync to update.");
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
    const response = await getUniverseConfig();
    setGroups(response.groups);
    setEditable(response.editable);
    setManagedMessage(response.message || "Managed by Moomoo. Run moomoo-sync to update.");
    if (nextMessage) {
      setMessage(nextMessage);
    }
  }

  async function handleCreateGroup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const groupId = normalizeGroupId(newGroupName);
    if (!groupId) {
      setError("Enter a group name before creating it.");
      return;
    }
    if (groups.some((group) => group.id === groupId)) {
      setError(`${groupId} already exists.`);
      return;
    }

    setBusyKey("create:group");
    setError(null);
    setMessage(null);
    try {
      await replaceUniverseGroup(groupId, []);
      setNewGroupName("");
      await reloadGroups(`${groupId} group created.`);
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : String(mutationError));
    } finally {
      setBusyKey(null);
    }
  }

  async function handleAddTicker(event: FormEvent<HTMLFormElement>, group: UniverseGroup) {
    event.preventDefault();
    const normalizedTicker = (tickerInputs[group.id] || "").trim().toUpperCase();
    if (!normalizedTicker) {
      setError("Enter a ticker before adding it to a universe.");
      return;
    }

    setBusyKey(`add:${group.id}`);
    setError(null);
    setMessage(null);
    try {
      await addUniverseTicker(group.id, normalizedTicker);
      setTickerInputs((current) => ({ ...current, [group.id]: "" }));
      await reloadGroups(`${normalizedTicker} added to ${group.name}.`);
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

  async function handleDeleteGroup(group: UniverseGroup) {
    if (!window.confirm(`Delete ${group.name}?`)) {
      return;
    }

    setBusyKey(`delete-group:${group.id}`);
    setError(null);
    setMessage(null);
    try {
      await deleteUniverseGroup(group.id);
      setTickerInputs((current) => {
        const next = { ...current };
        delete next[group.id];
        return next;
      });
      await reloadGroups(`${group.name} deleted.`);
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
          <p>{editable ? "Add, remove, and copy local universe members without starting a data refresh." : managedMessage}</p>
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
        {editable ? (
          <form className="universe-create-form" onSubmit={handleCreateGroup}>
            <label className="control-field">
              <span className="control-label">New group</span>
              <input
                aria-label="New universe group"
                value={newGroupName}
                onChange={(event) => setNewGroupName(event.target.value)}
                placeholder="ai_watch"
                disabled={busyKey !== null}
              />
            </label>
            <button
              type="submit"
              className="secondary-action-button"
              disabled={busyKey !== null}
            >
              <FolderPlus size={15} aria-hidden="true" />
              Add group
            </button>
          </form>
        ) : (
          <div className="status-banner">{managedMessage}</div>
        )}

        <div className="universe-list">
          {phase === "loading" || phase === "idle" ? (
            <div className="table-empty">Loading universes...</div>
          ) : groups.length > 0 ? (
            groups.map((group) => (
              <UniverseGroupCard
                key={group.id}
                group={group}
                busyKey={busyKey}
                tickerValue={tickerInputs[group.id] || ""}
                editable={editable}
                onTickerChange={(nextValue) =>
                  setTickerInputs((current) => ({ ...current, [group.id]: nextValue }))
                }
                onAddTicker={(event) => handleAddTicker(event, group)}
                onCopy={() => handleCopy(group)}
                onDeleteGroup={() => handleDeleteGroup(group)}
                onDeleteTicker={(tickerToDelete) => handleDeleteTicker(group, tickerToDelete)}
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
  tickerValue,
  editable,
  onTickerChange,
  onAddTicker,
  onCopy,
  onDeleteGroup,
  onDeleteTicker,
}: {
  group: UniverseGroup;
  busyKey: string | null;
  tickerValue: string;
  editable: boolean;
  onTickerChange: (value: string) => void;
  onAddTicker: (event: FormEvent<HTMLFormElement>) => void;
  onCopy: () => void;
  onDeleteGroup: () => void;
  onDeleteTicker: (ticker: string) => void;
}) {
  return (
    <article className="universe-card universe-card-wide">
      <div className="universe-card-header">
        <div className="universe-title-row">
          <h2>{group.name}</h2>
          <span className="universe-group-key mono">({group.id})</span>
        </div>
        <div className="universe-card-actions">
          <button
            type="button"
            className="icon-button"
            aria-label={`Copy ${group.name} tickers`}
            title={`Copy ${group.name} tickers`}
            onClick={onCopy}
          >
            <Copy size={16} aria-hidden="true" />
          </button>
          {editable ? (
            <button
              type="button"
              className="delete-group-button"
              disabled={busyKey === `delete-group:${group.id}`}
              onClick={onDeleteGroup}
            >
              Delete
            </button>
          ) : null}
        </div>
      </div>

      <div className="universe-ticker-list">
        {group.tickers.length > 0 ? (
          group.tickers.map((ticker) => (
            <span className="universe-ticker-chip" key={ticker}>
              <Link
                className="ticker-link mono"
                title={`Open ${ticker} chart`}
                to={`/market/${encodeURIComponent(ticker)}`}
              >
                {ticker}
              </Link>
              {editable ? (
                <button
                  type="button"
                  className="chip-delete-button"
                  aria-label={`Delete ${ticker} from ${group.name}`}
                  title={`Delete ${ticker} from ${group.name}`}
                  disabled={busyKey === `delete:${group.id}:${ticker}`}
                  onClick={() => onDeleteTicker(ticker)}
                >
                  x
                </button>
              ) : null}
            </span>
          ))
        ) : (
          <span className="universe-empty-note">No tickers yet.</span>
        )}
      </div>

      {editable ? (
        <form className="universe-card-add-form" onSubmit={onAddTicker}>
          <input
            aria-label={`Ticker to add to ${group.name}`}
            value={tickerValue}
            onChange={(event) => onTickerChange(event.target.value.toUpperCase())}
            placeholder="Add ticker..."
            disabled={busyKey !== null}
          />
          <button
            type="submit"
            className="secondary-action-button universe-card-add-button"
            disabled={busyKey !== null}
          >
            <Plus size={15} aria-hidden="true" />
            Add
          </button>
        </form>
      ) : null}
    </article>
  );
}

function normalizeGroupId(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
}
