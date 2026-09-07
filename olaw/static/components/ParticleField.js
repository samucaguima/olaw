/**
 * UI Element containing:
 * - A full-surface <canvas> on which particles swirl towards the pointer, leaving color-shifting
 *   trails behind them.
 * - A control panel exposing: particle count, attraction force, swirl, trail persistence,
 *   color shift, color mode, background color, clear / reset / pause and "Save PNG".
 *
 * Pointer interactions:
 * - Moving the pointer bends the field towards it. Fast moves push a "wake" along the way.
 * - Pressing detonates a shockwave and doubles the pull for as long as the pointer is held.
 * - When the pointer leaves, a slow virtual attractor takes over so the field stays alive.
 *
 * Keyboard: [C]lear, [R]eset, [S]ave, [P]ause, [H]ide panel.
 * Arrow keys / WASD move a virtual pointer when the canvas has focus, which makes the field
 * usable without a pointing device.
 *
 * Honors `prefers-reduced-motion: reduce` by starting with a calmer, slower field.
 */

/** Hard limits for the "particles" slider. */
const MIN_PARTICLES = 100;
const MAX_PARTICLES = 5000;

/** Particles are batched into `HUE_STEPS` x `WIDTH_CLASSES` paths to keep draw calls low. */
const HUE_STEPS = 32;
const WIDTH_CLASSES = 3;

/** Line width / opacity of the "core" (sharp) pass, per width class. */
const CORE_WIDTHS = [0.85, 1.5, 2.6];
const CORE_ALPHAS = [0.1, 0.16, 0.26];

/**
 * Multiplier / opacity of the "glow" (blurry) pass, per width class.
 * Only the two fastest classes get one: it is the expensive pass, and slow particles barely
 * benefit from it.
 */
const GLOW_SCALE = 3.2;
const GLOW_ALPHAS = [0, 0.022, 0.035];

/** Population and fade rate the opacities above are calibrated for. See `getExposure()`. */
const REFERENCE_COUNT = 1400;
const REFERENCE_FADE = 0.051;

/** Simulation constants. Expressed in CSS pixels and "per 60fps frame" units. */
const PHYSICS = {
  influence: 260, // Numerator of the distance falloff: higher means a wider reach
  soften: 120, // Prevents forces from exploding when the pointer sits on top of a particle
  core: 48, // Radius of the repulsive "eye" of the vortex
  corePush: 2.8, // Strength of that repulsion
  drag: 0.938, // Velocity kept from one frame to the next
  maxSpeed: 26, // Speed cap, in pixels per frame
  ambient: 0.07, // Strength of the ambient flow field (keeps the field alive when idle)
  wake: 0.022, // How much pointer velocity is transferred to nearby particles
  maxWake: 1.8,
  pressBoost: 1.85, // Force multiplier while the pointer is held down
  burstRadius: 340, // Reach of the shockwave triggered on pointer down
  burstImpulse: 17,
  edgeMargin: 30, // Particles wrap around once they are this far outside of the canvas
};

/** Delay (ms) after which the virtual attractor takes over from an inactive pointer. */
const IDLE_DELAY = 1600;

/**
 * The glow pass is by far the most expensive one: it is dropped after `GLOW_GRACE_MS` spent
 * below `GLOW_MIN_FPS`, and only restored when the load is lowered (fewer particles, reset).
 * Responsiveness comes first.
 */
const GLOW_MIN_FPS = 38;
const GLOW_GRACE_MS = 1200;

/** Values restored by the "Reset" button. */
const DEFAULT_PARAMS = {
  count: 1400,
  force: 0.55,
  swirl: 0.75,
  trail: 0.82,
  colorShift: 0.35,
  colorMode: "speed",
  background: "#070811",
};

/** Same, when `prefers-reduced-motion: reduce` is detected. */
const REDUCED_MOTION_PARAMS = {
  ...DEFAULT_PARAMS,
  count: 600,
  force: 0.3,
  swirl: 0.35,
  trail: 0.55,
  colorShift: 0.1,
};

/** Background presets. "Paper" matches the background color of the rest of the app. */
const BACKGROUNDS = [
  { label: "Ink", value: "#070811" },
  { label: "Deep sea", value: "#04141c" },
  { label: "Plum", value: "#15071b" },
  { label: "Slate", value: "#1b1f24" },
  { label: "Paper", value: "#f7f6f2" },
  { label: "Bone", value: "#e8e2d5" },
];

/** Available "color mode" options: determines what drives the hue of a particle. */
const COLOR_MODES = [
  { value: "speed", label: "Speed" },
  { value: "angle", label: "Direction" },
  { value: "distance", label: "Distance to pointer" },
  { value: "orbit", label: "Orbits" },
];

/** Sliders exposed by the control panel, in display order. */
const SLIDERS = [
  {
    param: "count",
    label: "Particles",
    min: MIN_PARTICLES,
    max: MAX_PARTICLES,
    step: 50,
    format: (value) => String(Math.round(value)),
  },
  {
    param: "force",
    label: "Attraction force",
    min: 0,
    max: 1.5,
    step: 0.01,
    format: (v) => v.toFixed(2),
  },
  {
    param: "swirl",
    label: "Swirl",
    min: 0,
    max: 1.5,
    step: 0.01,
    format: (v) => v.toFixed(2),
  },
  {
    param: "trail",
    label: "Trail persistence",
    min: 0,
    max: 1,
    step: 0.01,
    format: (v) => v.toFixed(2),
  },
  {
    param: "colorShift",
    label: "Color shift",
    min: 0,
    max: 1,
    step: 0.01,
    format: (v) => v.toFixed(2),
  },
];

/** Keys steering the virtual pointer, as `[x, y]` directions. */
const DIRECTION_KEYS = {
  arrowleft: [-1, 0],
  arrowright: [1, 0],
  arrowup: [0, -1],
  arrowdown: [0, 1],
  a: [-1, 0],
  d: [1, 0],
  w: [0, -1],
  s: [0, 1],
};

export class ParticleField extends HTMLElement {
  /** Reference to the <canvas> element. */
  canvasRef = null;

  /** 2D rendering context of `this.canvasRef`. */
  ctx = null;

  /** Reference to the control panel. */
  panelRef = null;

  /** Reference to the `aria-live` region used to report actions back to the user. */
  statusRef = null;

  /** Reference to the "fps / particles" readout. */
  readoutRef = null;

  /** User-controlled settings. See `DEFAULT_PARAMS`. */
  params = { ...DEFAULT_PARAMS };

  /** Settings the "Reset" button restores. */
  defaults = { ...DEFAULT_PARAMS };

  /**
   * Particle state, as flat typed arrays of length `MAX_PARTICLES`.
   * `agility` scales how strongly a particle answers the pointer (nimble particles orbit close
   * and fast, sluggish ones lag behind), `hueOffset` gives each trail its own tint.
   */
  positionX = new Float32Array(MAX_PARTICLES);
  positionY = new Float32Array(MAX_PARTICLES);
  previousX = new Float32Array(MAX_PARTICLES);
  previousY = new Float32Array(MAX_PARTICLES);
  velocityX = new Float32Array(MAX_PARTICLES);
  velocityY = new Float32Array(MAX_PARTICLES);
  seed = new Float32Array(MAX_PARTICLES);
  agility = new Float32Array(MAX_PARTICLES);
  hueOffset = new Float32Array(MAX_PARTICLES);

  /** Number of particles currently simulated. Always <= `MAX_PARTICLES`. */
  count = 0;

  /** Pointer state, in CSS pixels. `vx` / `vy` are expressed in pixels per frame. */
  pointer = {
    x: 0,
    y: 0,
    vx: 0,
    vy: 0,
    active: false,
    down: false,
    lastMoveAt: 0,
  };

  /** Direction the virtual (keyboard) pointer is currently being pushed towards. */
  keyboardPointer = { x: 0, y: 0 };

  /** Expanding rings drawn after a pointer press: `{x, y, age}`. */
  bursts = [];

  /** Position of the halo on the previous frame, used to measure how fast it travels. */
  auraPrevious = { x: 0, y: 0 };

  /** Canvas size in CSS pixels, and the device pixel ratio it was drawn at. */
  width = 0;
  height = 0;
  dpr = 1;

  /** `true` when the background color is dark enough for additive blending. */
  isDarkBackground = true;

  /** Cached `hsl()` strings, one per hue step. Rebuilt when the background changes. */
  palette = [];

  /** Animation state. */
  animationId = null;
  lastFrameAt = 0;
  elapsed = 0;
  fps = 60;
  readoutAt = 0;

  /** `true` while the simulation is on hold. */
  paused = false;

  /** Glow pass budget: see `GLOW_MIN_FPS`. */
  glowEnabled = true;
  slowFor = 0;

  /** `true` while a PNG export is in flight. Encoding a large canvas is not instant. */
  exporting = false;

  /** Observes size changes of the host element. */
  resizeObserver = null;

  /** Timeout clearing `this.statusRef`. */
  statusTimeout = null;

  connectedCallback() {
    // Enforce singleton
    for (const node of [...document.querySelectorAll("particle-field")].slice(
      1,
    )) {
      node.remove();
    }

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      this.defaults = { ...REDUCED_MOTION_PARAMS };
      this.params = { ...REDUCED_MOTION_PARAMS };
    }

    this.renderInnerHTML();

    // Grab shared element references
    this.canvasRef = this.querySelector("canvas");
    this.ctx = this.canvasRef.getContext("2d", { alpha: false });
    this.panelRef = this.querySelector(".panel");
    this.statusRef = this.querySelector(".status");
    this.readoutRef = this.querySelector(".readout");

    this.bindControls();
    this.bindPointer();

    document.addEventListener("keydown", this.handleKeyDown);

    this.resizeObserver = new ResizeObserver(this.handleResize);
    this.resizeObserver.observe(this);

    this.applyBackground(this.params.background);
    this.handleResize();
    this.setCount(this.params.count);
    this.clear();

    this.lastFrameAt = performance.now();
    this.animationId = requestAnimationFrame(this.frame);
  }

  disconnectedCallback() {
    cancelAnimationFrame(this.animationId);
    clearTimeout(this.statusTimeout);
    this.resizeObserver?.disconnect();
    document.removeEventListener("keydown", this.handleKeyDown);
    document.removeEventListener("keyup", this.handleKeyUp);
    window.removeEventListener("blur", this.releaseKeyboardPointer);
  }

  /*----------------------------------------------------------------------------
   * Sizing
   *--------------------------------------------------------------------------*/

  /**
   * Matches the canvas' backing store to its CSS size, and rescales particles accordingly.
   * @returns {void}
   */
  handleResize = () => {
    const rect = this.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    const dpr = Math.min(2, window.devicePixelRatio || 1);

    if (width === this.width && height === this.height && dpr === this.dpr) {
      return;
    }

    // Keep the composition when the surface is resized
    const scaleX = this.width ? width / this.width : 1;
    const scaleY = this.height ? height / this.height : 1;

    for (let i = 0; i < this.count; i++) {
      this.positionX[i] *= scaleX;
      this.positionY[i] *= scaleY;
      this.previousX[i] = this.positionX[i];
      this.previousY[i] = this.positionY[i];
    }

    this.width = width;
    this.height = height;
    this.dpr = dpr;

    this.canvasRef.width = Math.round(width * dpr);
    this.canvasRef.height = Math.round(height * dpr);
    this.canvasRef.style.width = `${width}px`;
    this.canvasRef.style.height = `${height}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.ctx.lineCap = "round";
    this.ctx.lineJoin = "round";

    if (!this.pointer.active) {
      this.pointer.x = width / 2;
      this.pointer.y = height / 2;
    }

    this.clear();
  };

  /*----------------------------------------------------------------------------
   * Particles
   *--------------------------------------------------------------------------*/

  /**
   * (Re)initializes particles in the `[from, to[` range, spreading them across the surface.
   * @param {number} from
   * @param {number} to
   * @returns {void}
   */
  seedParticles = (from, to) => {
    const width = this.width || window.innerWidth;
    const height = this.height || window.innerHeight;

    for (let i = from; i < to; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = Math.random() * 1.5;

      this.positionX[i] = Math.random() * width;
      this.positionY[i] = Math.random() * height;
      this.previousX[i] = this.positionX[i];
      this.previousY[i] = this.positionY[i];
      this.velocityX[i] = Math.cos(angle) * speed;
      this.velocityY[i] = Math.sin(angle) * speed;
      this.seed[i] = Math.random() * Math.PI * 2;
      this.agility[i] = 0.55 + Math.random() * 0.9;
      this.hueOffset[i] = (Math.random() - 0.5) * 46;
    }
  };

  /**
   * Grows or shrinks the simulated population, keeping existing particles in place.
   * @param {number} count
   * @returns {void}
   */
  setCount = (count) => {
    const next = Math.min(
      MAX_PARTICLES,
      Math.max(MIN_PARTICLES, Math.round(count)),
    );

    if (next > this.count) {
      this.seedParticles(this.count, next);
    }

    // Lightening the load is a chance to get the glow pass back
    if (next < this.count) {
      this.glowEnabled = true;
      this.slowFor = 0;
    }

    this.count = next;
    this.params.count = next;
  };

  /*----------------------------------------------------------------------------
   * Pointer
   *--------------------------------------------------------------------------*/

  /**
   * Wires pointer events on the canvas.
   * `pointerrawupdate` is used when available: it fires more often than `pointermove`,
   * which makes the field react to a moving pointer without waiting for the next frame.
   * @returns {void}
   */
  bindPointer = () => {
    const moveEvent =
      "onpointerrawupdate" in window ? "pointerrawupdate" : "pointermove";

    this.canvasRef.addEventListener(moveEvent, this.handlePointerMove, {
      passive: true,
    });
    this.canvasRef.addEventListener("pointerdown", this.handlePointerDown);
    this.canvasRef.addEventListener("pointerup", this.handlePointerUp);
    this.canvasRef.addEventListener("pointercancel", this.handlePointerUp);
    this.canvasRef.addEventListener("pointerleave", this.handlePointerLeave);
    this.canvasRef.addEventListener("contextmenu", (e) => e.preventDefault());
  };

  /**
   * Tracks pointer position and velocity.
   * Coalesced samples are replayed so that fast flicks are not reduced to a single jump.
   * @param {PointerEvent} e
   * @returns {void}
   */
  handlePointerMove = (e) => {
    const rect = this.canvasRef.getBoundingClientRect();
    const samples = e.getCoalescedEvents ? e.getCoalescedEvents() : [];

    for (const sample of samples.length ? samples : [e]) {
      const x = sample.clientX - rect.left;
      const y = sample.clientY - rect.top;

      if (this.pointer.active) {
        this.pointer.vx = this.pointer.vx * 0.55 + (x - this.pointer.x) * 0.45;
        this.pointer.vy = this.pointer.vy * 0.55 + (y - this.pointer.y) * 0.45;
      }

      this.pointer.x = x;
      this.pointer.y = y;
    }

    this.pointer.active = true;
    this.pointer.lastMoveAt = performance.now();
  };

  /**
   * Starts a shockwave and boosts the pull for as long as the pointer is held.
   * @param {PointerEvent} e
   * @returns {void}
   */
  handlePointerDown = (e) => {
    e.preventDefault();
    this.canvasRef.setPointerCapture?.(e.pointerId);
    this.canvasRef.focus({ preventScroll: true });

    const rect = this.canvasRef.getBoundingClientRect();
    this.pointer.x = e.clientX - rect.left;
    this.pointer.y = e.clientY - rect.top;
    this.pointer.active = true;
    this.pointer.down = true;
    this.pointer.lastMoveAt = performance.now();

    this.burst(this.pointer.x, this.pointer.y);
  };

  /**
   * @param {PointerEvent} e
   * @returns {void}
   */
  handlePointerUp = (e) => {
    this.canvasRef.releasePointerCapture?.(e.pointerId);
    this.pointer.down = false;
  };

  /**
   * @returns {void}
   */
  handlePointerLeave = () => {
    this.pointer.down = false;
    this.pointer.active = false;
  };

  /**
   * Pushes every particle within `PHYSICS.burstRadius` away from `(x, y)` and records a ring.
   * @param {number} x
   * @param {number} y
   * @returns {void}
   */
  burst = (x, y) => {
    const radius = PHYSICS.burstRadius;

    for (let i = 0; i < this.count; i++) {
      const dx = this.positionX[i] - x;
      const dy = this.positionY[i] - y;
      const distance = Math.hypot(dx, dy);

      if (distance > radius) {
        continue;
      }

      const impulse = (1 - distance / radius) * PHYSICS.burstImpulse;
      const norm = distance || 0.001;

      this.velocityX[i] += (dx / norm) * impulse;
      this.velocityY[i] += (dy / norm) * impulse;
    }

    this.bursts.push({ x, y, age: 0 });

    if (this.bursts.length > 8) {
      this.bursts.shift();
    }
  };

  /*----------------------------------------------------------------------------
   * Simulation
   *--------------------------------------------------------------------------*/

  /**
   * Animation loop: advances the simulation then draws it.
   * @param {number} now - Timestamp provided by `requestAnimationFrame`.
   * @returns {void}
   */
  frame = (now) => {
    this.animationId = requestAnimationFrame(this.frame);

    // Normalized delta: 1 == one frame at 60fps. Clamped so that tab switches don't blow up.
    const delta = Math.min(80, now - this.lastFrameAt) || 16.7;
    const step = Math.min(2.5, delta / 16.667);

    this.lastFrameAt = now;

    if (this.paused) {
      this.updateReadout(now);
      return;
    }

    this.fps = this.fps * 0.9 + (1000 / delta) * 0.1;
    this.elapsed += delta / 1000;

    // The first couple of seconds (page load, first paints) are not representative
    this.slowFor =
      this.fps < GLOW_MIN_FPS && this.elapsed > 2 ? this.slowFor + delta : 0;

    if (this.glowEnabled && this.slowFor > GLOW_GRACE_MS) {
      this.glowEnabled = false;
      this.setStatus("Glow pass dropped to keep the field responsive.");
    }

    this.update(step);
    this.draw(step);
    this.updateReadout(now);
  };

  /**
   * Returns the point particles are currently attracted to, and how strongly.
   * Falls back to a slow virtual attractor when the pointer has been idle.
   * @returns {{x: number, y: number, strength: number, live: boolean}}
   */
  getAttractor = () => {
    const idleFor = performance.now() - this.pointer.lastMoveAt;

    if (this.pointer.active || idleFor < IDLE_DELAY) {
      return { x: this.pointer.x, y: this.pointer.y, strength: 1, live: true };
    }

    // Lissajous curve, so that the composition keeps evolving while unattended
    const t = this.elapsed * 0.22;
    const x = this.width * (0.5 + 0.32 * Math.sin(t * 1.1));
    const y = this.height * (0.5 + 0.3 * Math.sin(t * 1.7 + 0.9));

    return { x, y, strength: 0.55, live: false };
  };

  /**
   * Advances every particle by `step` frames.
   * @param {number} step
   * @returns {void}
   */
  update = (step) => {
    const attractor = this.getAttractor();
    const boost = this.pointer.down ? PHYSICS.pressBoost : 1;
    const pullBase = this.params.force * 2.2 * attractor.strength * boost;
    const spinBase = this.params.swirl * 2.4 * attractor.strength * boost;
    const ambient = PHYSICS.ambient * (attractor.live ? 1 : 2.2);
    const drag = Math.pow(PHYSICS.drag, step);
    const margin = PHYSICS.edgeMargin;
    const wrapWidth = this.width + margin * 2;
    const wrapHeight = this.height + margin * 2;

    // Pointer velocity is consumed here, then decays: a flick shoves particles, a still
    // pointer does not.
    const wakeX = Math.max(
      -PHYSICS.maxWake,
      Math.min(PHYSICS.maxWake, this.pointer.vx * PHYSICS.wake),
    );
    const wakeY = Math.max(
      -PHYSICS.maxWake,
      Math.min(PHYSICS.maxWake, this.pointer.vy * PHYSICS.wake),
    );

    for (let i = 0; i < this.count; i++) {
      this.previousX[i] = this.positionX[i];
      this.previousY[i] = this.positionY[i];

      const dx = attractor.x - this.positionX[i];
      const dy = attractor.y - this.positionY[i];
      const distance = Math.sqrt(dx * dx + dy * dy) || 0.001;
      const nx = dx / distance;
      const ny = dy / distance;
      const falloff = PHYSICS.influence / (distance + PHYSICS.soften);

      // Radial pull + tangential spin: together they turn the pointer into a vortex
      const pull = pullBase * this.agility[i] * falloff;
      const spin = spinBase * this.agility[i] * falloff;

      let ax = nx * pull - ny * spin;
      let ay = ny * pull + nx * spin;

      // Keeps an "eye" at the center of the vortex instead of a collapsed dot
      if (distance < PHYSICS.core) {
        const push = (1 - distance / PHYSICS.core) * PHYSICS.corePush;
        ax -= nx * push;
        ay -= ny * push;
      }

      // Wake left by a moving pointer
      const wakeFalloff = 180 / (distance + 180);
      ax += wakeX * wakeFalloff;
      ay += wakeY * wakeFalloff;

      // Ambient flow field: cheap stand-in for curl noise, keeps the field breathing
      const s = this.seed[i];
      ax +=
        Math.sin(this.positionY[i] * 0.0055 + this.elapsed * 0.7 + s) * ambient;
      ay +=
        Math.cos(this.positionX[i] * 0.0055 + this.elapsed * 0.6 + s * 1.3) *
        ambient;

      let vx = (this.velocityX[i] + ax * step) * drag;
      let vy = (this.velocityY[i] + ay * step) * drag;

      const speed = Math.hypot(vx, vy);

      if (speed > PHYSICS.maxSpeed) {
        vx = (vx / speed) * PHYSICS.maxSpeed;
        vy = (vy / speed) * PHYSICS.maxSpeed;
      }

      this.velocityX[i] = vx;
      this.velocityY[i] = vy;

      let x = this.positionX[i] + vx * step;
      let y = this.positionY[i] + vy * step;

      // Wrap around the edges
      if (x < -margin) x += wrapWidth;
      else if (x > this.width + margin) x -= wrapWidth;

      if (y < -margin) y += wrapHeight;
      else if (y > this.height + margin) y -= wrapHeight;

      this.positionX[i] = x;
      this.positionY[i] = y;
    }

    this.pointer.vx *= Math.pow(0.82, step);
    this.pointer.vy *= Math.pow(0.82, step);

    this.applyKeyboardPointer(step);

    for (const ring of this.bursts) {
      ring.age += step;
    }

    this.bursts = this.bursts.filter((ring) => ring.age < 42);
  };

  /**
   * Moves the virtual pointer while arrow / WASD keys are held.
   * @param {number} step
   * @returns {void}
   */
  applyKeyboardPointer = (step) => {
    const { x, y } = this.keyboardPointer;

    if (!x && !y) {
      return;
    }

    const speed = 11 * step;

    this.pointer.vx = this.pointer.vx * 0.5 + x * speed * 0.5;
    this.pointer.vy = this.pointer.vy * 0.5 + y * speed * 0.5;
    this.pointer.x = Math.max(
      0,
      Math.min(this.width, this.pointer.x + x * speed),
    );
    this.pointer.y = Math.max(
      0,
      Math.min(this.height, this.pointer.y + y * speed),
    );
    this.pointer.active = true;
    this.pointer.lastMoveAt = performance.now();
  };

  /*----------------------------------------------------------------------------
   * Rendering
   *--------------------------------------------------------------------------*/

  /**
   * Draws one frame: fades the previous one (which is what creates the trails), then strokes
   * every particle as a segment going from its previous position to its current one.
   * @param {number} step
   * @returns {void}
   */
  draw = (step) => {
    const ctx = this.ctx;
    const attractor = this.getAttractor();
    const baseHue = this.elapsed * this.params.colorShift * 90 + 200;
    const paths = new Array(HUE_STEPS * WIDTH_CLASSES).fill(null);
    const hueSpan = HUE_STEPS / 360;
    const halfWidth = this.width * 0.5;
    const halfHeight = this.height * 0.5;

    // Trails: instead of clearing, paint a translucent layer of background color over the
    // previous frame. The lower the alpha, the longer the trails.
    const fade = 0.45 * Math.pow(1 - this.params.trail, 1.6) + 0.022;

    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = Math.min(1, fade * step);
    ctx.fillStyle = this.params.background;
    ctx.fillRect(0, 0, this.width, this.height);

    for (let i = 0; i < this.count; i++) {
      const x = this.positionX[i];
      const y = this.positionY[i];
      const px = this.previousX[i];
      const py = this.previousY[i];

      // Particle wrapped around this frame: skip the segment rather than draw across the canvas
      if (Math.abs(x - px) > halfWidth || Math.abs(y - py) > halfHeight) {
        continue;
      }

      const vx = this.velocityX[i];
      const vy = this.velocityY[i];
      const speed = Math.hypot(vx, vy);

      let hue = baseHue + this.hueOffset[i];

      switch (this.params.colorMode) {
        case "angle":
          hue += (Math.atan2(vy, vx) * 180) / Math.PI;
          break;
        case "distance":
          hue += Math.hypot(attractor.x - x, attractor.y - y) * 0.14;
          break;
        case "orbit":
          hue += (this.agility[i] - 0.55) * 420;
          break;
        default:
          hue += speed * 14;
      }

      const hueIndex =
        Math.floor((((hue % 360) + 360) % 360) * hueSpan) % HUE_STEPS;
      const widthClass = speed < 1.2 ? 0 : speed < 4.5 ? 1 : 2;
      const bucket = widthClass * HUE_STEPS + hueIndex;

      if (!paths[bucket]) {
        paths[bucket] = new Path2D();
      }

      paths[bucket].moveTo(px, py);
      // Motionless particles still get a dot, thanks to `lineCap: round`
      paths[bucket].lineTo(speed < 0.05 ? x + 0.01 : x, y);
    }

    const exposure = this.getExposure(fade);

    // Additive blending makes overlapping trails glow, which only reads well on dark grounds
    ctx.globalCompositeOperation = this.isDarkBackground
      ? "lighter"
      : "source-over";

    // Pass 1: wide and faint (glow). Skipped on light backgrounds, where it only muddies colors.
    if (this.isDarkBackground && this.glowEnabled) {
      for (let widthClass = 1; widthClass < WIDTH_CLASSES; widthClass++) {
        ctx.lineWidth = CORE_WIDTHS[widthClass] * GLOW_SCALE;
        ctx.globalAlpha = GLOW_ALPHAS[widthClass] * exposure;
        this.strokeBuckets(paths, widthClass);
      }
    }

    // Pass 2: thin and bright (core)
    for (let widthClass = 0; widthClass < WIDTH_CLASSES; widthClass++) {
      ctx.lineWidth = CORE_WIDTHS[widthClass];
      ctx.globalAlpha =
        CORE_ALPHAS[widthClass] * exposure * (this.isDarkBackground ? 1 : 2.4);
      this.strokeBuckets(paths, widthClass);
    }

    this.drawPointerAura(attractor, baseHue, fade);

    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  };

  /**
   * Opacity correction applied to every particle.
   *
   * Trails settle where what is painted on each frame equals what the fade removes, so
   * without this correction raising the particle count or the trail persistence would not
   * make the field richer, only whiter. Light is therefore rationed by population and by
   * fade rate.
   *
   * @param {number} fade - Alpha of the background layer painted on each frame.
   * @returns {number}
   */
  getExposure = (fade) => {
    const density = Math.min(
      1.6,
      Math.max(0.5, Math.sqrt(REFERENCE_COUNT / this.count)),
    );
    const persistence = Math.min(1.4, Math.max(0.4, fade / REFERENCE_FADE));

    return density * persistence;
  };

  /**
   * Strokes every non-empty hue bucket of a given width class.
   * @param {(Path2D|null)[]} paths
   * @param {number} widthClass
   * @returns {void}
   */
  strokeBuckets = (paths, widthClass) => {
    const offset = widthClass * HUE_STEPS;

    for (let hueIndex = 0; hueIndex < HUE_STEPS; hueIndex++) {
      const path = paths[offset + hueIndex];

      if (path) {
        this.ctx.strokeStyle = this.palette[hueIndex];
        this.ctx.stroke(path);
      }
    }
  };

  /**
   * Draws the halo following the pointer, plus the rings left by pointer presses.
   *
   * The halo is painted on every frame, so a halo standing still would pile up on the same
   * pixels until it burns out to white. Its opacity therefore follows how fast it travels
   * (a still pointer barely glows, a moving one leaves a comet) and how quickly trails fade.
   *
   * @param {{x: number, y: number, live: boolean}} attractor
   * @param {number} baseHue
   * @param {number} fade - Alpha of the background layer painted on each frame.
   * @returns {void}
   */
  drawPointerAura = (attractor, baseHue, fade) => {
    const ctx = this.ctx;
    const hue = Math.round(((baseHue % 360) + 360) % 360);
    const travelled = Math.hypot(
      attractor.x - this.auraPrevious.x,
      attractor.y - this.auraPrevious.y,
    );

    this.auraPrevious.x = attractor.x;
    this.auraPrevious.y = attractor.y;

    const motion = Math.min(1, travelled / 7);
    const radius =
      90 +
      Math.min(150, travelled * 4.5) +
      (this.pointer.down ? 80 : 0) * (attractor.live ? 1 : 0);
    const intensity =
      (attractor.live ? 0.13 : 0.09) *
      (0.22 + 0.78 * motion) *
      Math.min(1, fade / REFERENCE_FADE) *
      (this.isDarkBackground ? 1 : 0.35);

    const gradient = ctx.createRadialGradient(
      attractor.x,
      attractor.y,
      0,
      attractor.x,
      attractor.y,
      radius,
    );
    gradient.addColorStop(0, `hsla(${hue}, 100%, 74%, ${intensity})`);
    gradient.addColorStop(
      0.3,
      `hsla(${(hue + 30) % 360}, 100%, 66%, ${intensity * 0.4})`,
    );
    gradient.addColorStop(
      0.65,
      `hsla(${(hue + 60) % 360}, 100%, 60%, ${intensity * 0.1})`,
    );
    gradient.addColorStop(1, "hsla(0, 0%, 0%, 0)");

    ctx.globalAlpha = 1;
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(attractor.x, attractor.y, radius, 0, Math.PI * 2);
    ctx.fill();

    for (const ring of this.bursts) {
      const progress = ring.age / 42;

      ctx.globalAlpha =
        (1 - progress) * 0.55 * (this.isDarkBackground ? 1 : 0.7);
      ctx.strokeStyle = `hsl(${(hue + 60) % 360}, 100%, ${this.isDarkBackground ? 70 : 45}%)`;
      ctx.lineWidth = 2.5 * (1 - progress) + 0.4;
      ctx.beginPath();
      ctx.arc(ring.x, ring.y, ring.age * 8 + 6, 0, Math.PI * 2);
      ctx.stroke();
    }
  };

  /**
   * Rebuilds the hue lookup table and reads the luminance of the background, which decides
   * whether particles are blended additively or not.
   * @param {string} background - Hex color.
   * @returns {void}
   */
  applyBackground = (background) => {
    this.params.background = background;

    const hex = background.replace("#", "");
    const value = parseInt(
      hex.length === 3 ? hex.replace(/(.)/g, "$1$1") : hex,
      16,
    );
    const r = (value >> 16) & 255;
    const g = (value >> 8) & 255;
    const b = value & 255;

    // Rec. 709 relative luminance
    this.isDarkBackground = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 < 0.5;
    this.classList.toggle("on-light-canvas", !this.isDarkBackground);

    const lightness = this.isDarkBackground ? 62 : 42;
    const saturation = this.isDarkBackground ? 96 : 82;

    this.palette = new Array(HUE_STEPS);

    for (let i = 0; i < HUE_STEPS; i++) {
      this.palette[i] =
        `hsl(${Math.round((i * 360) / HUE_STEPS)}, ${saturation}%, ${lightness}%)`;
    }

    this.style.setProperty("--canvas-background", background);
  };

  /**
   * Wipes the trails, repainting the surface with the current background color.
   * @returns {void}
   */
  clear = () => {
    this.ctx.globalAlpha = 1;
    this.ctx.globalCompositeOperation = "source-over";
    this.ctx.fillStyle = this.params.background;
    this.ctx.fillRect(0, 0, this.width, this.height);
    this.bursts = [];
  };

  /**
   * Restores default settings and re-seeds the whole population.
   * @returns {void}
   */
  reset = () => {
    this.params = { ...this.defaults };
    this.setCount(this.defaults.count);
    this.seedParticles(0, this.count);
    this.velocityX.fill(0);
    this.velocityY.fill(0);
    this.pointer.vx = 0;
    this.pointer.vy = 0;
    this.glowEnabled = true;
    this.slowFor = 0;
    this.applyBackground(this.defaults.background);
    this.clear();
    this.syncControls();
  };

  /**
   * Downloads the current state of the canvas as a PNG file.
   * @returns {void}
   */
  saveScreenshot = () => {
    if (this.exporting) {
      return;
    }

    this.exporting = true;
    this.setStatus("Exporting PNG ...");

    this.canvasRef.toBlob((blob) => {
      this.exporting = false;

      if (!blob) {
        this.setStatus(
          "Screenshot failed: this browser refused to export the canvas.",
        );
        return;
      }

      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      const filename = `particle-field-${stamp}.png`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = url;
      link.download = filename;
      link.click();

      // Some browsers only read the blob after the click has been processed
      setTimeout(() => URL.revokeObjectURL(url), 10000);

      this.setStatus(`Screenshot saved as ${filename}.`);
    }, "image/png");
  };

  /*----------------------------------------------------------------------------
   * Controls
   *--------------------------------------------------------------------------*/

  /**
   * Wires every input, swatch and button of the control panel.
   * @returns {void}
   */
  bindControls = () => {
    for (const input of this.querySelectorAll(`input[type="range"]`)) {
      input.addEventListener("input", (e) => {
        const param = e.target.dataset.param;
        const value = parseFloat(e.target.value);

        if (param === "count") {
          this.setCount(value);
        } else {
          this.params[param] = value;
        }

        this.updateOutput(param, this.params[param]);
      });
    }

    this.querySelector("#pf-color-mode").addEventListener("change", (e) => {
      this.params.colorMode = e.target.value;
    });

    for (const button of this.querySelectorAll("button[data-background]")) {
      button.addEventListener("click", (e) => {
        e.preventDefault();
        this.pickBackground(button.dataset.background);
      });
    }

    this.querySelector("#pf-background-custom").addEventListener(
      "input",
      (e) => {
        this.pickBackground(e.target.value);
      },
    );

    const actions = {
      clear: () => {
        this.clear();
        this.setStatus("Trails cleared.");
      },
      reset: () => {
        this.reset();
        this.setStatus("Field reset to its default settings.");
      },
      pause: () => this.togglePause(),
      save: () => this.saveScreenshot(),
      "toggle-panel": () => this.togglePanel(),
    };

    for (const [action, handler] of Object.entries(actions)) {
      this.querySelector(`button[data-action="${action}"]`).addEventListener(
        "click",
        (e) => {
          e.preventDefault();
          handler();
        },
      );
    }

    document.addEventListener("keyup", this.handleKeyUp);
    window.addEventListener("blur", this.releaseKeyboardPointer);
  };

  /**
   * Drops the virtual pointer, for instance when the window loses focus while a direction key
   * is held down.
   * @returns {void}
   */
  releaseKeyboardPointer = () => {
    this.keyboardPointer.x = 0;
    this.keyboardPointer.y = 0;
  };

  /**
   * Applies a background color and wipes the surface, so trails and ground always match.
   * @param {string} value - Hex color.
   * @returns {void}
   */
  pickBackground = (value) => {
    this.applyBackground(value);
    this.clear();

    for (const button of this.querySelectorAll("button[data-background]")) {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.background === value),
      );
    }

    this.querySelector("#pf-background-custom").value = value;
  };

  /**
   * @returns {void}
   */
  togglePause = () => {
    this.paused = !this.paused;

    const button = this.querySelector(`button[data-action="pause"]`);
    button.textContent = this.paused ? "Resume" : "Pause";
    button.setAttribute("aria-pressed", String(this.paused));

    this.setStatus(this.paused ? "Simulation paused." : "Simulation resumed.");
  };

  /**
   * Collapses / expands the control panel, leaving the field unobstructed.
   * @returns {void}
   */
  togglePanel = () => {
    const collapsed = this.classList.toggle("is-collapsed");
    const button = this.querySelector(`button[data-action="toggle-panel"]`);

    button.textContent = collapsed ? "Show controls" : "Hide";
    button.setAttribute("aria-expanded", String(!collapsed));
  };

  /**
   * Reflects `this.params` back into the control panel.
   * @returns {void}
   */
  syncControls = () => {
    for (const slider of SLIDERS) {
      this.querySelector(`#pf-${slider.param}`).value =
        this.params[slider.param];
      this.updateOutput(slider.param, this.params[slider.param]);
    }

    this.querySelector("#pf-color-mode").value = this.params.colorMode;
    this.querySelector("#pf-background-custom").value = this.params.background;

    for (const button of this.querySelectorAll("button[data-background]")) {
      const pressed = button.dataset.background === this.params.background;
      button.setAttribute("aria-pressed", String(pressed));
    }
  };

  /**
   * Updates the value displayed next to a slider.
   * @param {string} param
   * @param {number} value
   * @returns {void}
   */
  updateOutput = (param, value) => {
    const output = this.querySelector(`output[data-for="${param}"]`);
    const slider = SLIDERS.find((entry) => entry.param === param);

    if (output && slider) {
      output.textContent = slider.format(value);
    }
  };

  /**
   * Reports an action back to the user, in a region screen readers announce.
   * @param {string} text
   * @returns {void}
   */
  setStatus = (text) => {
    this.statusRef.textContent = text;

    clearTimeout(this.statusTimeout);
    this.statusTimeout = setTimeout(
      () => (this.statusRef.textContent = ""),
      5000,
    );
  };

  /**
   * Refreshes the "fps / particles" readout, at most 4 times per second.
   * @param {number} now
   * @returns {void}
   */
  updateReadout = (now) => {
    if (now - this.readoutAt < 250) {
      return;
    }

    this.readoutAt = now;
    const glow =
      this.isDarkBackground && !this.glowEnabled ? " · glow off" : "";

    this.readoutRef.textContent = this.paused
      ? `paused · ${this.count} particles`
      : `${Math.round(this.fps)} fps · ${this.count} particles${glow}`;
  };

  /**
   * Handles shortcuts and the virtual (keyboard) pointer.
   * @param {KeyboardEvent} e
   * @returns {void}
   */
  handleKeyDown = (e) => {
    const tagName = e.target?.tagName;
    const key = e.key.toLowerCase();

    // Sliders and selects own every key. Buttons only own the keys that activate them.
    if (["INPUT", "SELECT", "TEXTAREA"].includes(tagName)) {
      return;
    }

    if (tagName === "BUTTON" && (key === " " || key === "enter")) {
      return;
    }
    const direction = DIRECTION_KEYS[key];

    if (direction) {
      e.preventDefault();
      this.keyboardPointer.x = direction[0];
      this.keyboardPointer.y = direction[1];
      return;
    }

    switch (key) {
      case "c":
        this.clear();
        this.setStatus("Trails cleared.");
        break;
      case "r":
        this.reset();
        this.setStatus("Field reset to its default settings.");
        break;
      case "s":
        this.saveScreenshot();
        break;
      case "h":
        this.togglePanel();
        break;
      case "p":
      case " ":
        e.preventDefault();
        this.togglePause();
        break;
      default:
        break;
    }
  };

  /**
   * Releases the virtual pointer.
   * @param {KeyboardEvent} e
   * @returns {void}
   */
  handleKeyUp = (e) => {
    const direction = DIRECTION_KEYS[e.key.toLowerCase()];

    if (!direction) {
      return;
    }

    if (this.keyboardPointer.x === direction[0]) {
      this.keyboardPointer.x = 0;
    }

    if (this.keyboardPointer.y === direction[1]) {
      this.keyboardPointer.y = 0;
    }
  };

  renderInnerHTML = () => {
    const sliders = SLIDERS.map(
      (slider) => /*html*/ `
        <div class="control">
          <label for="pf-${slider.param}">${slider.label}</label>
          <div class="control-row">
            <input
              type="range"
              id="pf-${slider.param}"
              data-param="${slider.param}"
              min="${slider.min}"
              max="${slider.max}"
              step="${slider.step}"
              value="${this.params[slider.param]}" />
            <output data-for="${slider.param}">${slider.format(this.params[slider.param])}</output>
          </div>
        </div>`,
    ).join("");

    const swatches = BACKGROUNDS.map(
      (background) => /*html*/ `
        <button
          type="button"
          class="swatch"
          data-background="${background.value}"
          style="--swatch: ${background.value}"
          aria-pressed="${background.value === this.params.background}"
          title="${background.label}">
          <span class="visually-hidden">${background.label}</span>
        </button>`,
    ).join("");

    const colorModes = COLOR_MODES.map(
      (mode) => /*html*/ `
        <option value="${mode.value}" ${mode.value === this.params.colorMode ? "selected" : ""}>
          ${mode.label}
        </option>`,
    ).join("");

    this.innerHTML = /*html*/ `
    <canvas
      tabindex="0"
      role="img"
      aria-label="Particle field reacting to the pointer. Use arrow keys to steer it."></canvas>

    <div class="panel">
      <div class="panel-head">
        <h2>Particle field</h2>
        <button
          type="button"
          data-action="toggle-panel"
          aria-controls="pf-panel-body"
          aria-expanded="true">
          Hide
        </button>
      </div>

      <div class="panel-body" id="pf-panel-body">
        ${sliders}

        <div class="control">
          <label for="pf-color-mode">Color mode</label>
          <select id="pf-color-mode">${colorModes}</select>
        </div>

        <div class="control">
          <span class="label" id="pf-background-label">Background</span>
          <div class="swatches" role="group" aria-labelledby="pf-background-label">
            ${swatches}
            <label class="swatch custom" title="Custom background color">
              <span class="visually-hidden">Custom background color</span>
              <input type="color" id="pf-background-custom" value="${this.params.background}" />
            </label>
          </div>
        </div>

        <div class="actions">
          <button type="button" data-action="clear">Clear</button>
          <button type="button" data-action="reset">Reset</button>
          <button type="button" data-action="pause" aria-pressed="false">Pause</button>
          <button type="button" class="primary" data-action="save">Save PNG</button>
        </div>

        <p class="readout" aria-hidden="true"></p>
        <p class="status" role="status" aria-live="polite"></p>

        <p class="hint">
          Move the pointer to bend the field, press to detonate a shockwave and hold to pull
          harder. Shortcuts: <kbd>C</kbd>lear, <kbd>R</kbd>eset, <kbd>S</kbd>ave,
          <kbd>P</kbd>ause, <kbd>H</kbd>ide. Arrow keys steer the field without a mouse.
        </p>
      </div>
    </div>
    `;
  };
}
customElements.define("particle-field", ParticleField);
