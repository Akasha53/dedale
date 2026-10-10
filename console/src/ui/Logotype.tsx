// Logotype sAIfe : « s » et « fe » en graisse normale, « AI » en gras, même couleur.
// Le jeu de mots safe + AI se lit sans couleur ajoutée. Le logo graphique ne change pas.
import "./logotype.css";

export function Logotype({ className }: { className?: string }) {
  return (
    <span className={className ? `logotype ${className}` : "logotype"}>
      s<b>AI</b>fe
    </span>
  );
}
