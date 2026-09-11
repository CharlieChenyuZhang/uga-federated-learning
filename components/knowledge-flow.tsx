"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useAnimate } from "motion/react";
import {
  BookOpen,
  Building2,
  Cpu,
  FlaskConical,
  Lightbulb,
  Network,
  Pause,
  Play,
  Users,
} from "lucide-react";

// A conceptual diagram, independent of the number of seeded institutions.
// Motion drives the SVG strokes directly, without per-frame React state updates.
const branches = [
  "M75 50 C165 50 155 140 250 140",
  "M75 140 C150 140 175 140 250 140",
  "M75 230 C165 230 155 140 250 140",
  "M250 140 C345 140 335 50 425 50",
  "M250 140 C325 140 350 140 425 140",
  "M250 140 C345 140 335 230 425 230",
];
const nodes = [
  { label: "Campuses", icon: Building2, x: 15, y: 17.86 },
  { label: "Research teams", icon: FlaskConical, x: 15, y: 50 },
  { label: "Educators", icon: Users, x: 15, y: 82.14 },
  { label: "Models", icon: Cpu, x: 85, y: 17.86 },
  { label: "Teaching tools", icon: BookOpen, x: 85, y: 50 },
  { label: "New ideas", icon: Lightbulb, x: 85, y: 82.14 },
];
type Playback = { pause: () => void; play: () => void; cancel: () => void };

const motionPreference = "(prefers-reduced-motion: reduce)";
function subscribeMotionPreference(onChange: () => void) {
  const media = window.matchMedia(motionPreference);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
const getMotionPreference = () => window.matchMedia(motionPreference).matches;
const getServerMotionPreference = () => null;

export default function KnowledgeFlow() {
  const [scope, animate] = useAnimate<HTMLDivElement>();
  // Keep server/client hydration identical and react to live OS preference changes.
  const reduceMotion = useSyncExternalStore<boolean | null>(
    subscribeMotionPreference,
    getMotionPreference,
    getServerMotionPreference,
  );
  const [paused, setPaused] = useState(false);
  const playback = useRef<Playback[]>([]);
  const manualPause = useRef(false);

  useEffect(() => {
    // Render a static diagram until the device preference has been resolved.
    if (reduceMotion !== false || !scope.current) return;
    const root = scope.current;
    const animations: Playback[] = [];
    root.querySelectorAll<SVGPathElement>("[data-stream]").forEach((path) => {
      const branch = Number(path.dataset.stream);
      animations.push(
        animate(
          path,
          { strokeDashoffset: [0, -1] },
          {
            duration: 3.8 + (branch % 3) * 0.6,
            delay: branch * 0.47,
            ease: "linear",
            repeat: Infinity,
          },
        ),
      );
    });
    animations.push(
      animate(
        ".flow-liquid",
        {
          borderRadius: [
            "44% 56% 62% 38% / 44% 38% 62% 56%",
            "62% 38% 44% 56% / 56% 62% 38% 44%",
            "44% 56% 62% 38% / 44% 38% 62% 56%",
          ],
          rotate: [0, 180, 360],
          scale: [0.96, 1.04, 0.96],
        },
        { duration: 18, ease: "linear", repeat: Infinity },
      ),
    );
    playback.current = animations;
    let inView = true;
    const syncPlayback = () => {
      const shouldPause = manualPause.current || document.hidden || !inView;
      animations.forEach((control) =>
        shouldPause ? control.pause() : control.play(),
      );
    };
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      syncPlayback();
    });
    observer.observe(root);
    document.addEventListener("visibilitychange", syncPlayback);
    syncPlayback();
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", syncPlayback);
      animations.forEach((control) => control.cancel());
      playback.current = [];
    };
  }, [animate, reduceMotion, scope]);

  function togglePause() {
    const next = !manualPause.current;
    manualPause.current = next;
    setPaused(next);
    playback.current.forEach((control) =>
      next ? control.pause() : control.play(),
    );
  }

  return (
    <figure className="knowledge-flow">
      <div className="flow-heading">
        <span>IDEAS IN MOTION</span>
        <button
          type="button"
          className="flow-playback"
          onClick={togglePause}
          disabled={reduceMotion !== false}
          aria-label={
            paused ? "Resume information flow" : "Pause information flow"
          }
          aria-pressed={paused}
        >
          {paused || reduceMotion !== false ? (
            <Play size={13} />
          ) : (
            <Pause size={13} />
          )}
          {reduceMotion !== false
            ? "Reduced motion"
            : paused
              ? "Resume"
              : "Pause"}
        </button>
      </div>
      <div className="flow-stage" ref={scope}>
        <svg
          viewBox="0 0 500 280"
          preserveAspectRatio="none"
          className="flow-connections"
          aria-hidden="true"
        >
          {branches.map((d, i) => (
            <g key={d}>
              <path
                d={d}
                fill="none"
                stroke="#7286c0"
                strokeOpacity=".24"
                strokeWidth="1"
              />
              {reduceMotion === false && (
                <>
                  <path
                    className="flow-stream"
                    data-stream={i}
                    d={d}
                    pathLength={1}
                    fill="none"
                    stroke={i < 3 ? "#9caefe" : "#8bddcf"}
                    strokeOpacity=".25"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeDasharray="0.11 0.89"
                  />
                  <path
                    className="flow-stream"
                    data-stream={i}
                    d={d}
                    pathLength={1}
                    fill="none"
                    stroke={i < 3 ? "#becaff" : "#a9eee1"}
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    strokeDasharray="0.014 0.986"
                  />
                </>
              )}
            </g>
          ))}
        </svg>
        {nodes.map(({ label, icon: Icon, x, y }, index) => (
          <div
            key={label}
            className={`flow-node ${index > 2 ? "flow-node-out" : ""}`}
            style={{ left: `${x}%`, top: `${y}%` }}
          >
            <span className="flow-node-icon">
              <Icon size={18} />
            </span>
            <span>{label}</span>
          </div>
        ))}
        <div className="flow-hub">
          <div className="flow-liquid" aria-hidden="true" />
          <div className="flow-hub-content">
            <Network size={25} />
            <strong>
              Shared
              <br />
              possibilities
            </strong>
          </div>
        </div>
      </div>
      <figcaption>
        A vision for connected workspaces and the ideas they can create.
      </figcaption>
    </figure>
  );
}
