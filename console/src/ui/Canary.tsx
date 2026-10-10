// Le mot « canary » reste (vocabulaire du métier). Sa première occurrence dans
// un texte porte une courte définition, au survol comme au toucher : l'élément
// prend le focus, et la définition s'affiche tant qu'il le garde.
export const DEF_CANARY = "Faux secret posé par sAIfe, qu'un agent honnête ne touche jamais";

export function TexteCanary({ texte }: { texte: string }) {
  const m = /\bcanary\b/i.exec(texte);
  if (!m) return <>{texte}</>;
  return (
    <>
      {texte.slice(0, m.index)}
      <abbr className="canary" title={DEF_CANARY} tabIndex={0} data-def={DEF_CANARY}>
        {m[0]}
      </abbr>
      {texte.slice(m.index + m[0].length)}
    </>
  );
}
