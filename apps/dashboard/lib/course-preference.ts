// Il corso scelto sul sito ("Inscrever" su un corso JAV nelle scuole porta a
// /c/<slug>?curso=<id>). Fra la registrazione e il primo figlio aggiunto ci
// sono la conferma dell'email e il login: il corso si ricorda qui, nel
// browser, e il modulo "Aggiungi un figlio" lo trova già scelto. Se la
// famiglia finisce il giro su un altro telefono, il modulo chiede il corso
// comunque: è solo una comodità, non un dato su cui si conta.

const KEY = "jav_course_pref";

export function saveCoursePreference(courseId: string | null): void {
  if (typeof window === "undefined" || !courseId) return;
  try {
    window.localStorage.setItem(KEY, courseId);
  } catch {
    // Navigazione privata o spazio pieno: il modulo chiederà il corso.
  }
}

export function readCoursePreference(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}
