"use client";

import { usePeriodLabel } from "@/components/ext-courses/common";
import { StatTile } from "@/components/ui/stat-tile";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { ExtAccounts } from "@/lib/ext-courses";
import { useI18n } from "@/lib/i18n/provider";

/** I conti dei corsi esterni come li calcola il server (service.accounts):
 *  mese per mese e corso per corso. `coach`: la vista del treinador, che
 *  vede le mensilità pagate dei suoi gruppi e la sua parte. */
export function ExtAccountsTables({ data, coach = false }: { data: ExtAccounts; coach?: boolean }) {
  const { t, fmt } = useI18n();
  const period = usePeriodLabel();
  const money = (cents: number) => fmt.euro(cents);
  const empty = data.months.length === 0 && data.courses.length === 0;
  return (
    <div className="space-y-6">
      <div className={coach ? "grid gap-3 sm:grid-cols-2" : "grid gap-3 sm:grid-cols-2 lg:grid-cols-4"}>
        {coach ? (
          <>
            <StatTile label={t("ext.acc.myEarnings")} value={data.total.coach_cents} format={money} />
            <StatTile label={t("ext.acc.paidFees")} value={data.total.income_cents} format={money} />
          </>
        ) : (
          <>
            <StatTile label={t("ext.acc.income")} value={data.total.income_cents} format={money} />
            <StatTile label={t("ext.acc.coach")} value={data.total.coach_cents} format={money} />
            <StatTile label={t("ext.acc.jav")} value={data.total.jav_cents} format={money} />
            <StatTile label={t("ext.acc.due")} value={data.due_cents} format={money} />
          </>
        )}
      </div>
      {empty ? (
        <p className="rounded-2xl bg-ink-50 p-4 text-sm text-ink-500">{t("ext.acc.empty", { year: data.year })}</p>
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>{t("ext.acc.month")}</TH>
                <TH className="text-right">{coach ? t("ext.acc.paidFees") : t("ext.acc.income")}</TH>
                <TH className="text-right">{coach ? t("ext.acc.myEarnings") : t("ext.acc.coach")}</TH>
                {!coach && <TH className="text-right">{t("ext.acc.jav")}</TH>}
              </TR>
            </THead>
            <TBody>
              {data.months.map((m) => (
                <TR key={m.period}>
                  <TD className="capitalize">{period(m.period)}</TD>
                  <TD className="text-right tabular-nums">{fmt.euro(m.income_cents)}</TD>
                  <TD className="text-right tabular-nums font-semibold">{fmt.euro(m.coach_cents)}</TD>
                  {!coach && <TD className="text-right tabular-nums">{fmt.euro(m.jav_cents)}</TD>}
                </TR>
              ))}
            </TBody>
          </Table>
          <Table>
            <THead>
              <TR>
                <TH>{t("ext.acc.course")}</TH>
                <TH className="text-right">{coach ? t("ext.acc.paidFees") : t("ext.acc.income")}</TH>
                <TH className="text-right">{coach ? t("ext.acc.myEarnings") : t("ext.acc.coach")}</TH>
                {!coach && <TH className="text-right">{t("ext.acc.jav")}</TH>}
                {!coach && <TH className="text-right">{t("ext.acc.due")}</TH>}
              </TR>
            </THead>
            <TBody>
              {data.courses.map((c) => (
                <TR key={c.course_id}>
                  <TD><span className="block font-semibold text-ink-900">{c.school_name}</span><span className="block text-xs text-ink-500">{c.name}</span></TD>
                  <TD className="text-right tabular-nums">{fmt.euro(c.income_cents)}</TD>
                  <TD className="text-right tabular-nums font-semibold">{fmt.euro(c.coach_cents)}</TD>
                  {!coach && <TD className="text-right tabular-nums">{fmt.euro(c.jav_cents)}</TD>}
                  {!coach && <TD className="text-right tabular-nums">{fmt.euro(c.due_cents)}</TD>}
                </TR>
              ))}
            </TBody>
          </Table>
        </>
      )}
    </div>
  );
}

/** L'anno dei conti: questo e i due prima. */
export function yearOptions(): number[] {
  const y = new Date().getFullYear();
  return [y, y - 1, y - 2];
}
