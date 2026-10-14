"use client";

import { motion, useMotionTemplate, useMotionValue, useSpring } from "motion/react";
import { useRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { usePrefersReducedMotion } from "@/lib/motion";

/** A card that tilts in 3D toward the pointer, with a holographic sheen
 *  (the `.holo` layer in globals.css) that follows it -- the "trading card"
 *  surface of athlete cards and badges. Flat and still with reduced motion
 *  or on touch-only screens, where there is no pointer to follow. */
export function TiltCard({ children, className, max = 12 }: { children: ReactNode; className?: string; max?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = usePrefersReducedMotion();
  const rx = useSpring(useMotionValue(0), { stiffness: 220, damping: 18 });
  const ry = useSpring(useMotionValue(0), { stiffness: 220, damping: 18 });
  const sx = useMotionValue(50);
  const sy = useMotionValue(50);
  const so = useSpring(useMotionValue(0), { stiffness: 200, damping: 30 });
  const transform = useMotionTemplate`perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg)`;

  function onMove(e: React.PointerEvent) {
    if (reduced || e.pointerType === "touch" || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    ry.set((px - 0.5) * 2 * max);
    rx.set(-(py - 0.5) * 2 * max);
    sx.set(px * 100);
    sy.set(py * 100);
    so.set(1);
  }
  function onLeave() {
    rx.set(0);
    ry.set(0);
    so.set(0);
  }

  return (
    <motion.div
      ref={ref}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      style={{
        transform: reduced ? undefined : transform,
        transformStyle: "preserve-3d",
        ["--shine-x" as string]: useMotionTemplate`${sx}%`,
        ["--shine-y" as string]: useMotionTemplate`${sy}%`,
        ["--shine-opacity" as string]: so,
      }}
      className={cn("holo will-change-transform", className)}
    >
      {children}
    </motion.div>
  );
}
