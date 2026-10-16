"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { AthleteMarks } from "@/components/club/person-marks";
import { BELTS, beltFor } from "@/lib/belts";
import { clubGet, clubSend, fullName, shortDate, type AthleteCard, type BeltHistory, type Course, type Roster } from "@/lib/club";
import { celebrate } from "@/lib/motion";

const S = (path: string) => `/staff${path}`;
const today = () => new Date().toISOString().slice(0, 10);

/** Attendance on the mat: pick the course and the day, then one tap per
 *  athlete. Big targets, made for a tablet held in one hand. */
export function AttendanceBoard() {
  const { data: courses, isLoading } = useQuery({ queryKey: ["club", "staff", "courses"], queryFn: () => clubGet<Course[]>(S("/courses")) });
  const [courseId, setCourseId] = useState<string>("");
  const [date, setDate] = useState(today);
  const selected = courseId || courses?.[0]?.id || "";
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: roster, isLoading: loadingRoster } = useQuery({
    queryKey: ["club", "staff", "roster", selected, date],
    queryFn: () => clubGet<Roster>(S(`/courses/${selected}/roster?date=${date}`)),
    enabled: !!selected,
  });

  async function mark(athleteId: string, present: boolean) {
    const key = ["club", "staff", "roster", selected, date];
    queryClient.setQueryData<Roster>(key, (r) => (r ? { ...r, rows: r.rows.map((x) => (x.athlete_id === athleteId ? { ...x, present } : x)) } : r));
    try {
      await clubSend(S(`/courses/${selected}/attendance`), "POST", { date, athlete_id: athleteId, present });
    } catch (e) {
      toast({ tone: "error", title: "Presenza non salvata", text: (e as Error).message });
      void queryClient.invalidateQueries({ queryKey: key });
    }
  }

  if (isLoading) return <Skeleton className="h-64" />;
  if (!courses?.length) return <EmptyState icon={<span className="text-3xl">📅</span>} title="Nessun corso" text="Quando la segreteria ti assegna un corso lo trovi qui." />;
  const rows = roster?.rows ?? [];
  const present = rows.filter((r) => r.present).length;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row gap-3">
        <Select value={selected} onChange={(e) => setCourseId(e.target.value)} aria-label="Corso">
          {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="sm:w-52" aria-label="Giorno" />
        <div className="sm:ml-auto rounded-2xl bg-ink-900 text-white px-5 flex items-center gap-2 h-11">
          <span className="font-display text-xl">{present}</span>
          <span className="text-xs text-ink-300">/ {rows.length} presenti</span>
        </div>
      </div>
      {loadingRoster ? <Skeleton className="h-64" /> : rows.length === 0 ? <EmptyState title="Nessun iscritto al corso" /> : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {rows.map((r) => (
            <motion.button
              key={r.athlete_id}
              whileTap={{ scale: 0.95 }}
              onClick={() => mark(r.athlete_id, !r.present)}
              className={`relative rounded-3xl p-4 text-left ring-2 cursor-pointer transition-colors ${r.present ? "bg-emerald-50 ring-emerald-400" : "bg-white ring-ink-100 hover:ring-ink-300"}`}
              aria-pressed={!!r.present}
            >
              <AnimatePresence>
                {r.present && (
                  <motion.span initial={{ scale: 0, rotate: -30 }} animate={{ scale: 1, rotate: 0 }} exit={{ scale: 0 }} className="absolute top-3 right-3 h-8 w-8 rounded-full bg-emerald-500 text-white flex items-center justify-center font-bold">✓</motion.span>
                )}
              </AnimatePresence>
              <div className="h-14 w-14 rounded-full overflow-hidden bg-gradient-to-br from-ink-200 to-ink-400 flex items-center justify-center font-display text-xl text-white mb-3">
                {r.photo_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={r.photo_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  r.first_name.slice(0, 1)
                )}
              </div>
              <p className="text-sm font-semibold text-ink-900 leading-tight">{r.first_name}<br />{r.last_name}</p>
              <div className="mt-2"><BeltBadge belt={r.belt} size="sm" showLabel={false} /></div>
            </motion.button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Passaggi di grado: find the athlete, pick the new belt (only higher ones
 *  are offered -- the API refuses the others anyway), and celebrate it. */
export function BeltAwardPanel() {
  const [q, setQ] = useState("");
  const { data: athletes, isLoading } = useQuery({
    queryKey: ["club", "staff", "athletes", q],
    queryFn: () => clubGet<AthleteCard[]>(S(`/athletes${q ? `?q=${encodeURIComponent(q)}` : ""}`)),
  });
  const [selected, setSelected] = useState<AthleteCard | null>(null);
  return (
    <div className="grid lg:grid-cols-[1fr_1.2fr] gap-6">
      <div className="space-y-3">
        <Input placeholder="Cerca un atleta…" value={q} onChange={(e) => setQ(e.target.value)} />
        {isLoading ? <Skeleton className="h-64" /> : (
          <div className="glass-card rounded-3xl divide-y divide-ink-100 overflow-hidden max-h-[520px] overflow-y-auto">
            {(athletes ?? []).map((a) => (
              <button key={a.id} onClick={() => setSelected(a)} className={`w-full flex items-center justify-between gap-3 px-4 py-3 text-left cursor-pointer hover:bg-ink-50 ${selected?.id === a.id ? "bg-brand-50" : ""}`}>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-ink-900 truncate">{fullName(a)} <AthleteMarks id={a.id} /></span>
                  <span className="block text-xs text-ink-500">{a.federal_age ?? a.season_age} anni (età federale)</span>
                </span>
                <BeltBadge belt={a.belt} size="sm" showLabel={false} />
              </button>
            ))}
            {(athletes ?? []).length === 0 && <p className="text-sm text-ink-500 p-6 text-center">Nessun atleta trovato.</p>}
          </div>
        )}
      </div>
      {selected ? <BeltAward athlete={selected} key={selected.id} /> : <EmptyState icon={<span className="text-3xl">🎖️</span>} title="Scegli un atleta" text="Per vedere le sue cinture e registrare un passaggio di grado." />}
    </div>
  );
}

function BeltAward({ athlete }: { athlete: AthleteCard }) {
  const { data: history } = useQuery({ queryKey: ["club", "staff", "belts", athlete.id], queryFn: () => clubGet<BeltHistory[]>(S(`/athletes/${athlete.id}/belts`)) });
  const currentRank = BELTS.findIndex((b) => b.code === (history?.[history.length - 1]?.code ?? athlete.belt?.code ?? "WHITE"));
  const higher = BELTS.slice(currentRank + 1);
  const [grade, setGrade] = useState(higher[0]?.code ?? "");
  const [awardedOn, setAwardedOn] = useState(today);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [ceremony, setCeremony] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();

  async function award() {
    const code = grade || higher[0]?.code;
    if (!code) return;
    setBusy(true);
    try {
      await clubSend(S(`/athletes/${athlete.id}/belts`), "POST", { grade: code, awarded_on: awardedOn, note: note || null });
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      setCeremony(code);
      void celebrate({ x: 0.6, y: 0.45 });
      setNote("");
    } catch (e) {
      toast({ tone: "error", title: "Passaggio non registrato", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="glass-card rounded-3xl p-5 space-y-5 relative overflow-hidden">
      <div>
        <h3 className="text-lg text-ink-900">{fullName(athlete)}</h3>
        <div className="mt-2"><BeltBadge belt={athlete.belt} /></div>
      </div>
      <ol className="space-y-2">
        {[...(history ?? [])].reverse().map((b) => (
          <li key={b.id} className="flex items-center justify-between gap-3 text-sm">
            <BeltBadge belt={b} size="sm" />
            <span className="text-xs text-ink-500">{shortDate(b.awarded_on)}</span>
          </li>
        ))}
      </ol>
      {higher.length === 0 ? (
        <Badge tone="accent">Grado massimo raggiunto</Badge>
      ) : (
        <div className="space-y-3 pt-4 border-t border-ink-100">
          <p className="font-display text-sm text-ink-900">Nuovo grado</p>
          <div className="flex flex-wrap gap-2">
            {higher.slice(0, 6).map((b) => (
              <motion.button
                key={b.code}
                whileHover={{ y: -3 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setGrade(b.code)}
                className={`rounded-2xl px-3 py-2.5 ring-2 cursor-pointer ${(grade || higher[0]?.code) === b.code ? "ring-brand-500 bg-brand-50" : "ring-ink-100 bg-white"}`}
              >
                <BeltBadge code={b.code} size="sm" />
              </motion.button>
            ))}
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="Data" htmlFor="belt-date"><Input id="belt-date" type="date" value={awardedOn} onChange={(e) => setAwardedOn(e.target.value)} /></Field>
            <Field label="Nota" htmlFor="belt-note"><Input id="belt-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="es. Esame di dicembre" /></Field>
          </div>
          <Button size="lg" className="w-full" loading={busy} onClick={award}>🎖️ Assegna la cintura</Button>
        </div>
      )}

      <AnimatePresence>
        {ceremony && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setCeremony(null)}
            className="absolute inset-0 z-10 bg-white/95 backdrop-blur flex flex-col items-center justify-center text-center p-6 cursor-pointer"
          >
            <motion.p initial={{ y: -10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="text-xs font-bold uppercase tracking-[0.25em] text-brand-600">Passaggio di grado</motion.p>
            <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 0.25, type: "spring", stiffness: 120, damping: 14 }} className="my-6 origin-left">
              <BeltBadge code={ceremony} size="lg" showLabel={false} />
            </motion.div>
            <motion.h3 initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.5, type: "spring" }} className="text-2xl text-ink-900">
              {athlete.first_name} è cintura {beltFor(ceremony).label.toLowerCase()}!
            </motion.h3>
            <p className="text-sm text-ink-500 mt-2">Tocca per continuare</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
