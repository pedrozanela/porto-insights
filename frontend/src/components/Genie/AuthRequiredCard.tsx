import type { AuthRequired } from "../../state/types";

const SERVICE_LABEL: Record<string, string> = {
  gmail: "Gmail",
  google_calendar: "Google Agenda",
  calendar: "Google Agenda",
  google_drive: "Google Drive",
  drive: "Google Drive",
};

// Card amigável quando uma conta Google ainda não foi conectada (Login OAuth pendente).
export function AuthRequiredCard({ auth }: { auth: AuthRequired[] }) {
  return (
    <div className="mb-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm">
      <div className="font-semibold text-amber-900">Conecte sua conta Google</div>
      <p className="mt-1 text-amber-800">
        Para responder sobre {auth.map((a) => SERVICE_LABEL[a.service] ?? a.service).join(", ")}, você
        precisa autorizar o acesso uma única vez no Catalog Explorer. O restante continua funcionando.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {auth.map((a) => (
          <a
            key={a.service}
            href={a.login_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700"
          >
            Conectar {SERVICE_LABEL[a.service] ?? a.service} →
          </a>
        ))}
      </div>
    </div>
  );
}
