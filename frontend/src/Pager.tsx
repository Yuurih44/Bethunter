export function Pager({
  page,
  total,
  size = 50,
  onPage,
}: {
  page: number;
  total: number;
  size?: number;
  onPage: (n: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="toolbar" aria-label="Paginação">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        Anterior
      </button>
      <span>
        Página {page} de {pages} · {total} registros
      </span>
      <button
        type="button"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Próxima
      </button>
    </div>
  );
}
