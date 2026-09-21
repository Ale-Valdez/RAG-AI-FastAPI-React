export function LoadingState({ label }: { label: string }) {
  return <p className="state muted">{label}</p>;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <section className="state">
      <h2>{title}</h2>
      <p className="muted">{detail}</p>
    </section>
  );
}

export function ErrorState({ message }: { message: string }) {
  return <p className="state error">{message}</p>;
}
