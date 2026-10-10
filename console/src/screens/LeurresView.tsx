import { useDonnees } from "../api/store";
import { horsExterne, Spinner, tempsRelatif } from "../ui/primitives";

export function LeurresView() {
  const { leurres: tous, chargement } = useDonnees();

  if (chargement) return <Spinner />;

  // Canaris des agents IA et canaris physiques. Les leurres L-xxxx de la
  // surface externe restent dans le backend, hors de la console.
  const leurres = tous.filter(horsExterne);
  const agents = leurres.filter((l) => l.source === "interne");
  const physiques = leurres.filter((l) => l.source !== "interne");
  const totalTouches = leurres.reduce((n, l) => n + (l.touches || 0), 0);

  return (
    <>
      <div className="grille-compteurs">
        <div className="compteur">
          <div className="lib">Canaris des agents IA</div>
          <div className="val">{agents.length}</div>
          <div className="sous">préfixe C- · mails, documents, outils</div>
        </div>
        <div className="compteur">
          <div className="lib">Canaris physiques</div>
          <div className="val">{physiques.length}</div>
          <div className="sous">locaux et serveurs</div>
        </div>
        <div className={`compteur ${totalTouches > 0 ? "alerte" : ""}`}>
          <div className="lib">Touches cumulées</div>
          <div className="val">{totalTouches}</div>
          <div className="sous">tous canaris confondus</div>
        </div>
      </div>

      <div className="panneau">
        <div className="titre">
          Inventaire des canaris
          <span className="droite">{leurres.length} canaris posés</span>
        </div>
        {leurres.length === 0 ? (
          <div className="vide">Aucun canari enregistré.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="grille">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Surface</th>
                  <th>Nature</th>
                  <th>Emplacement</th>
                  <th>Cadres</th>
                  <th style={{ textAlign: "right" }}>Touches</th>
                  <th>Dernière</th>
                </tr>
              </thead>
              <tbody>
                {[...leurres]
                  .sort((a, b) => (b.touches || 0) - (a.touches || 0))
                  .map((l) => (
                    <tr key={l.id}>
                      <td className="idc">{l.id}</td>
                      <td>
                        {l.surface}
                        <div className="pastille-nat">{l.source}</div>
                      </td>
                      <td>
                        {l.nature.replace(/_/g, " ")}
                        <div className="pastille-nat">{l.description}</div>
                      </td>
                      <td style={{ color: "var(--texte-doux)" }}>{l.emplacement}</td>
                      <td>
                        <div className="puces-tech">
                          {(l.techniques ?? []).map((t) => (
                            <span key={t} className="tag atlas">
                              {t}
                            </span>
                          ))}
                          {(l.risques ?? []).map((r) => (
                            <span key={r} className="tag risque">
                              {r}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <span
                          className={`touches ${
                            l.touches === 0 ? "zero" : l.touches >= 2 ? "chaud" : ""
                          }`}
                        >
                          {l.touches ?? 0}
                        </span>
                      </td>
                      <td style={{ color: "var(--texte-faible)", fontSize: 12 }}>
                        {l.derniere_touche ? tempsRelatif(l.derniere_touche) : "—"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
