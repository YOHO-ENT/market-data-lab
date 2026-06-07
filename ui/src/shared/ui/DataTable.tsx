export function DataTable({ children }: { children: React.ReactNode }) {
  return (
    <div className="data-table-wrap">
      <table className="data-table">{children}</table>
    </div>
  );
}
