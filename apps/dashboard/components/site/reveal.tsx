"use client";

import { MotionConfig, motion } from "motion/react";
import type { ReactNode } from "react";

/** Una sezione che entra salendo appena arriva sullo schermo, una volta
 *  sola. Con "riduci movimento" del sistema (MotionConfig "user") resta solo
 *  la dissolvenza, senza spostamenti. */
export function Reveal({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <MotionConfig reducedMotion="user">
      <motion.div
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
        className={className}
      >
        {children}
      </motion.div>
    </MotionConfig>
  );
}
