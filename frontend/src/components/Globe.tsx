import * as Cesium from 'cesium';
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { fetchAllCities } from '../lib/api';
import type { City, GlobeAction, HighlightPoint } from '../lib/types';

const ION_TOKEN = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;
const USE_BLACK_MARBLE_BASEMAP = true;
const BLACK_MARBLE_ASSET_ID = 3812;

const GLOW = '#FFD978';
const INK = '#F4F7FB';
const MIDNIGHT = '#020308';

export interface GlobeHandle {
  applyAction: (action: GlobeAction) => void;
  setAutoRotate: (on: boolean) => void;
  resetView: () => void;
}

export interface HoverState {
  city: City;
  x: number;
  y: number;
}

const DEFAULT_DESTINATION = Cesium.Cartesian3.fromDegrees(-28, 12, 17_200_000);
const DEFAULT_ORIENTATION = {
  heading: 0,
  pitch: Cesium.Math.toRadians(-90),
  roll: 0,
};

// Pitch -90° = straight down; keeps the Earth disk centered in the panel at all times.
const HIGHLIGHT_PITCH = Cesium.Math.toRadians(-90);
const SINGLE_HIGHLIGHT_ALTITUDE = 12_500_000;

interface Props {
  autoRotate?: boolean;
  onHover?: (state: HoverState | null) => void;
  onSelect?: (city: City) => void;
  /**
   * Year in [2012, 2035]. Dot sizes scale by the projected brightness at this
   * year vs the city's 2012 baseline, so scrubbing the time ribbon makes
   * brightening cities grow and darkening cities shrink in real time.
   */
  year?: number;
}

function color(css: string, alpha = 1) {
  return Cesium.Color.fromCssColorString(css).withAlpha(alpha);
}

/**
 * Color a city by VIIRS trend. Diverging scale, calibrated to be visibly
 * differentiated at small dot sizes:
 *   trend < -1  → saturated blue
 *   trend ≈ 0   → cream
 *   trend ≈ 2   → warm yellow
 *   trend ≈ 5   → orange
 *   trend ≥ 8   → deep red
 */
function trendColor(trend: number): Cesium.Color {
  if (trend < 0) {
    const t = Math.min(1, -trend / 3);
    const r = Math.round(170 - 110 * t);  // 170 → 60
    const g = Math.round(195 - 80 * t);   // 195 → 115
    const b = Math.round(230 + 10 * t);   // 230 → 240
    return Cesium.Color.fromBytes(r, g, b, 235);
  }
  // Multi-stop interpolation across 0 → 2 → 5 → 8 for stronger contrast.
  const stops = [
    { t: 0, r: 245, g: 230, b: 195 },  // cream
    { t: 2, r: 250, g: 190, b: 110 },  // warm yellow
    { t: 5, r: 240, g: 110, b: 70 },   // orange
    { t: 8, r: 210, g: 50, b: 50 },    // deep red
  ];
  const clamped = Math.min(8, trend);
  let i = 0;
  while (i < stops.length - 1 && clamped > stops[i + 1].t) i++;
  const lo = stops[i];
  const hi = stops[Math.min(i + 1, stops.length - 1)];
  const span = hi.t - lo.t || 1;
  const f = Math.max(0, Math.min(1, (clamped - lo.t) / span));
  const r = Math.round(lo.r + (hi.r - lo.r) * f);
  const g = Math.round(lo.g + (hi.g - lo.g) * f);
  const b = Math.round(lo.b + (hi.b - lo.b) * f);
  const alpha = trend > 4 ? 240 : 215;
  return Cesium.Color.fromBytes(r, g, b, alpha);
}

/** Population (millions) → screen-space pixel size for the city dot. */
function citySize(pop_m: number): number {
  return Math.max(2, Math.min(7, 2.2 + Math.log10(pop_m + 0.1) * 1.8));
}

/**
 * Paint the rate-of-change heatmap: one dot per city, colored by trend,
 * sized by population. Uses PointPrimitiveCollection (GPU-direct, no
 * per-entity React overhead) so thousands of points render at 60fps.
 */
function addCityHeatmap(viewer: Cesium.Viewer, cities: City[]): Cesium.PointPrimitiveCollection {
  const collection = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
  for (const c of cities) {
    // Cities whose Milky Way disappeared during the VIIRS record get a warmer
    // outline — a quiet visual badge that this place crossed a milestone.
    const hasMilestone = c.milky_way_lost != null || c.doubled != null;
    collection.add({
      position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat),
      pixelSize: citySize(c.pop),
      color: trendColor(c.trend),
      outlineColor: hasMilestone
        ? Cesium.Color.fromBytes(255, 217, 120, 165)
        : Cesium.Color.BLACK.withAlpha(0.55),
      outlineWidth: hasMilestone ? 1.1 : 0.5,
      // Depth-test against the globe so dots on the far side are hidden by the
      // sphere. Otherwise every dot renders on top of everything (the default
      // when disableDepthTestDistance is Infinity) and the back hemisphere
      // bleeds through into the front.
      scaleByDistance: new Cesium.NearFarScalar(800_000, 1.4, 18_000_000, 0.35),
      // City object stored on the primitive so picks can read it back.
      id: c,
    });
  }
  return collection;
}

interface HighlightOptions {
  primary?: boolean;
  index?: number;
  fadeInStart: Cesium.JulianDate;
  cityLookup: Map<string, City>;
}

/**
 * Cohesive highlight: amplifies the city's existing heatmap dot in place
 * rather than overlaying amber chrome on top of it. Three layers:
 *   1) A thin screen-space ring in the city's own heatmap color (pulses softly).
 *   2) A brighter "amplified" dot in the heatmap color (replaces the muted ambient dot).
 *   3) A clean label — no background card, just text + thin outline.
 * The original heatmap PointPrimitive stays put underneath; the entity layers
 * here render on top because Entities draw above PointPrimitiveCollections.
 */
function addHighlight(
  viewer: Cesium.Viewer,
  point: HighlightPoint,
  options: HighlightOptions,
): Cesium.Entity[] {
  const { primary = true, fadeInStart, cityLookup } = options;
  const seed = Math.abs(point.lat * 91.7 + point.lon * 37.3);
  const entities: Cesium.Entity[] = [];

  const lookupKey = `${point.lat.toFixed(2)},${point.lon.toFixed(2)}`;
  const city = cityLookup.get(lookupKey);
  const trend = city?.trend ?? 0;
  const dotColor = trendColor(trend);

  // 1) Thin pulse ring in the trend color (screen-space).
  entities.push(
    viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(point.lon, point.lat),
      point: {
        pixelSize: 1,
        color: Cesium.Color.TRANSPARENT,
        outlineColor: new Cesium.CallbackProperty((time) => {
          const t = Math.max(0, Cesium.JulianDate.secondsDifference(time ?? fadeInStart, fadeInStart));
          const fade = Math.min(1, t / 0.7);
          const pulse = 0.55 + Math.sin(t * 1.6 + seed) * 0.18;
          return dotColor.withAlpha((primary ? 0.55 : 0.32) * fade * pulse);
        }, false),
        outlineWidth: primary ? 22 : 14,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    }),
  );

  // 2) Brightened dot — sits exactly on top of the heatmap primitive.
  entities.push(
    viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(point.lon, point.lat),
      point: {
        pixelSize: primary ? 8 : 5.5,
        color: new Cesium.CallbackProperty((time) => {
          const t = Math.max(0, Cesium.JulianDate.secondsDifference(time ?? fadeInStart, fadeInStart));
          const fade = Math.min(1, t / 0.35);
          const pulse = 0.85 + Math.sin(t * 2.2 + seed) * 0.15;
          // Brighten the trend color via additive bias toward white.
          const r = Math.min(255, dotColor.red * 255 + 30);
          const g = Math.min(255, dotColor.green * 255 + 30);
          const b = Math.min(255, dotColor.blue * 255 + 30);
          return Cesium.Color.fromBytes(r, g, b, Math.round(245 * fade * pulse));
        }, false),
        outlineColor: Cesium.Color.fromBytes(20, 22, 30, 200),
        outlineWidth: 1,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance: new Cesium.NearFarScalar(900_000, 1.2, 14_000_000, 0.7),
      },
      label: point.label
        ? {
            text: point.label,
            font: `${primary ? 500 : 400} ${primary ? 12 : 11}px "Inter", sans-serif`,
            fillColor: Cesium.Color.fromCssColorString(INK).withAlpha(primary ? 0.95 : 0.78),
            outlineColor: Cesium.Color.fromCssColorString(MIDNIGHT).withAlpha(0.95),
            outlineWidth: 3,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            showBackground: false,
            pixelOffset: new Cesium.Cartesian2(0, primary ? -22 : -18),
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            scaleByDistance: new Cesium.NearFarScalar(1_000_000, 1, 14_000_000, 0.6),
            translucencyByDistance: new Cesium.NearFarScalar(1_000_000, 1, 16_000_000, 0.4),
          }
        : undefined,
    }),
  );

  return entities;
}

/** Thin geodesic arcs between successive highlights — quiet, in muted ink. */
function addConnectingArcs(
  viewer: Cesium.Viewer,
  points: HighlightPoint[],
  fadeInStart: Cesium.JulianDate,
): Cesium.Entity[] {
  if (points.length < 2) return [];
  const entities: Cesium.Entity[] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    const a = points[i];
    const b = points[i + 1];
    const arcDelay = 0.3 + i * 0.18;

    entities.push(
      viewer.entities.add({
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArrayHeights([
            a.lon, a.lat, 60_000,
            b.lon, b.lat, 60_000,
          ]),
          width: 0.8,
          arcType: Cesium.ArcType.GEODESIC,
          material: new Cesium.ColorMaterialProperty(
            new Cesium.CallbackProperty((time) => {
              const t = Math.max(0, Cesium.JulianDate.secondsDifference(time ?? fadeInStart, fadeInStart));
              const fade = Math.min(1, Math.max(0, (t - arcDelay) / 0.8));
              return Cesium.Color.fromCssColorString(INK).withAlpha(0.28 * fade);
            }, false),
          ),
        },
      }),
    );
  }
  return entities;
}

export const Globe = forwardRef<GlobeHandle, Props>(function Globe({ autoRotate = true, onHover, onSelect, year = 2025 }, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const clockStartRef = useRef<Cesium.JulianDate | null>(null);
  const rotateRef = useRef(autoRotate);
  const highlightsRef = useRef<Cesium.Entity[]>([]);
  const cityLookupRef = useRef<Map<string, City>>(new Map());
  const heatmapRef = useRef<Cesium.PointPrimitiveCollection | null>(null);
  const citiesRef = useRef<City[]>([]);

  useEffect(() => {
    rotateRef.current = autoRotate;
  }, [autoRotate]);

  useEffect(() => {
    if (!containerRef.current) return;

    if (ION_TOKEN) {
      Cesium.Ion.defaultAccessToken = ION_TOKEN;
    }

    const viewer = new Cesium.Viewer(containerRef.current, {
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      shouldAnimate: true,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    });
    viewerRef.current = viewer;
    clockStartRef.current = viewer.clock.currentTime.clone();

    (viewer.cesiumWidget.creditContainer as HTMLElement).style.display = 'none';
    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#000000');
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#02030A');

    // Atmosphere edge glow, shifted deep blue to match the night theme.
    if (viewer.scene.skyAtmosphere) {
      viewer.scene.skyAtmosphere.show = true;
      viewer.scene.skyAtmosphere.hueShift = -0.55;
      viewer.scene.skyAtmosphere.saturationShift = -0.3;
      viewer.scene.skyAtmosphere.brightnessShift = -0.4;
    }
    viewer.scene.fog.enabled = false;
    viewer.scene.globe.enableLighting = false;
    viewer.scene.globe.showGroundAtmosphere = false;
    if (viewer.scene.sun) viewer.scene.sun.show = false;
    if (viewer.scene.moon) viewer.scene.moon.show = false;
    // Cesium's bundled star field as the deep-space backdrop.
    if (viewer.scene.skyBox) viewer.scene.skyBox.show = true;

    viewer.imageryLayers.removeAll();

    if (ION_TOKEN && USE_BLACK_MARBLE_BASEMAP) {
      // NASA Black Marble (Earth at Night) via Cesium Ion. Already a nighttime
      // view of the planet — city lights bright, oceans dark — so the only
      // tuning we do is a mild brightness pullback so our diverging change-rate
      // dots remain the focal element on top.
      Cesium.IonImageryProvider.fromAssetId(BLACK_MARBLE_ASSET_ID)
        .then((provider) => {
          if (viewerRef.current !== viewer) return;
          const layer = viewer.imageryLayers.addImageryProvider(provider);
          layer.brightness = 1.0;
          layer.contrast = 1.0;
          layer.saturation = 1.0;
          layer.gamma = 1.0;
        })
        .catch((err) => {
          if (viewerRef.current === viewer) {
            console.warn('[Nightview] Black Marble unavailable.', err);
          }
        });
    } else {
      // Cesium ships Natural Earth II as a bundled, low-res tile set. No Ion token needed.
      // Darken + desaturate it so the continents read as nighttime, then our synthetic
      // city-light dots paint over the top.
      Cesium.TileMapServiceImageryProvider.fromUrl(
        Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII'),
      )
        .then((provider) => {
          // StrictMode double-mounts in dev; bail if this viewer was already destroyed.
          if (viewerRef.current !== viewer) return;
          const layer = viewer.imageryLayers.addImageryProvider(provider);
          layer.brightness = 0.38;
          layer.saturation = 0.35;
          layer.contrast = 1.28;
          layer.gamma = 1.18;
          layer.hue = -0.08;
        })
        .catch((err) => {
          if (viewerRef.current === viewer) {
            console.warn('[Nightview] Natural Earth II imagery unavailable.', err);
          }
        });
    }

    // Fetch the global city dataset and paint the rate-of-change heatmap.
    // This is the *default* visual: the story is on screen before any query.
    fetchAllCities()
      .then((res) => {
        if (viewerRef.current !== viewer) return;
        citiesRef.current = res.cities;
        heatmapRef.current = addCityHeatmap(viewer, res.cities);
        // Index by rounded lat/lon for fast trend lookup when highlighting.
        const lookup = new Map<string, City>();
        for (const c of res.cities) {
          lookup.set(`${c.lat.toFixed(2)},${c.lon.toFixed(2)}`, c);
        }
        cityLookupRef.current = lookup;
      })
      .catch((err) => {
        console.warn('[Nightview] city heatmap unavailable; backend may be down', err);
      });

    viewer.camera.setView({
      destination: DEFAULT_DESTINATION,
      orientation: DEFAULT_ORIENTATION,
    });

    const rotate = () => {
      if (rotateRef.current) {
        viewer.camera.rotate(Cesium.Cartesian3.UNIT_Z, -0.00028);
      }
    };
    viewer.scene.preRender.addEventListener(rotate);

    // Hover + click → city pick. ScreenSpaceEventHandler binds to the canvas,
    // not the React props, so we read latest callbacks via closures from refs.
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    // 20px pick window so the tiny 2-7px dots are forgiving to land on.
    const PICK_WINDOW = 20;
    const canvas = viewer.scene.canvas as HTMLCanvasElement;

    // Cesium pick can return entity-based primitives (highlight rings, labels)
    // whose .id is a Cesium.Entity, not a City. Duck-type to filter those out
    // — only City objects have `trend` + `lat` + `lon`.
    const cityFromPick = (picked: unknown): City | null => {
      if (!picked || typeof picked !== 'object') return null;
      const primitive = (picked as { primitive?: { id?: unknown } }).primitive;
      const candidate = primitive?.id ?? (picked as { id?: unknown }).id;
      if (
        candidate &&
        typeof candidate === 'object' &&
        'trend' in candidate &&
        'lat' in candidate &&
        'lon' in candidate &&
        typeof (candidate as City).trend === 'number'
      ) {
        return candidate as City;
      }
      return null;
    };

    handler.setInputAction((movement: Cesium.ScreenSpaceEventHandler.MotionEvent) => {
      const picked = viewer.scene.pick(movement.endPosition, PICK_WINDOW, PICK_WINDOW);
      const city = cityFromPick(picked);
      if (city) {
        canvas.style.cursor = 'pointer';
        onHoverRef.current?.({ city, x: movement.endPosition.x, y: movement.endPosition.y });
      } else {
        canvas.style.cursor = '';
        onHoverRef.current?.(null);
      }
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
    handler.setInputAction((movement: Cesium.ScreenSpaceEventHandler.PositionedEvent) => {
      const picked = viewer.scene.pick(movement.position, PICK_WINDOW, PICK_WINDOW);
      const city = cityFromPick(picked);
      if (city) {
        onSelectRef.current?.(city);
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    return () => {
      viewer.scene.preRender.removeEventListener(rotate);
      handler.destroy();
      viewer.destroy();
      viewerRef.current = null;
    };
  }, []);

  const onHoverRef = useRef(onHover);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onHoverRef.current = onHover;
    onSelectRef.current = onSelect;
  }, [onHover, onSelect]);

  // When the time-ribbon year changes, scale every heatmap dot by the
  // projected radiance at that year vs 2012 baseline. Brightening cities grow,
  // darkening cities shrink. Color (= trend) stays constant.
  useEffect(() => {
    const collection = heatmapRef.current;
    const cities = citiesRef.current;
    if (!collection || cities.length === 0) return;
    const yearsFromBaseline = year - 2012;
    for (let i = 0; i < collection.length; i += 1) {
      const primitive = collection.get(i);
      const city = cities[i];
      if (!city) continue;
      const projectedFactor = Math.pow(1 + city.trend / 100, yearsFromBaseline);
      // Use the projected factor directly (capped 0.3–4×). A 5%/yr city grows
      // ~3× by 2035; a -2%/yr city shrinks to ~0.63×. Very visible at a glance.
      const scale = Math.max(0.3, Math.min(4, projectedFactor));
      primitive.pixelSize = Math.max(0.8, Math.min(20, citySize(city.pop) * scale));
    }
  }, [year]);

  useImperativeHandle(ref, () => ({
    setAutoRotate(on: boolean) {
      rotateRef.current = on;
    },
    resetView() {
      const viewer = viewerRef.current;
      if (!viewer) return;
      highlightsRef.current.forEach((e) => viewer.entities.remove(e));
      highlightsRef.current = [];
      viewer.camera.flyTo({
        destination: DEFAULT_DESTINATION,
        orientation: DEFAULT_ORIENTATION,
        duration: 2.2,
        easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
        complete: () => {
          rotateRef.current = true;
        },
      });
    },
    applyAction(action: GlobeAction) {
      const viewer = viewerRef.current;
      const clockStart = clockStartRef.current;
      if (!viewer || !clockStart) return;

      rotateRef.current = false;
      const fadeInStart = viewer.clock.currentTime.clone();

      switch (action.type) {
        case 'fly_to': {
          const { lat, lon, label } = action.payload as {
            lat: number;
            lon: number;
            zoom?: number;
            label?: string;
          };
          highlightsRef.current.forEach((e) => viewer.entities.remove(e));
          highlightsRef.current = addHighlight(
            viewer,
            { lat, lon, label },
            { primary: true, fadeInStart, cityLookup: cityLookupRef.current },
          );
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(lon, lat, SINGLE_HIGHLIGHT_ALTITUDE),
            orientation: { heading: 0, pitch: HIGHLIGHT_PITCH, roll: 0 },
            duration: 2.4,
            easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
          });
          break;
        }
        case 'highlight_cells': {
          const { points = [] } = action.payload as { points: HighlightPoint[] };
          highlightsRef.current.forEach((e) => viewer.entities.remove(e));
          highlightsRef.current = [];
          if (points.length === 0) break;

          points.forEach((p, index) => {
            highlightsRef.current.push(
              ...addHighlight(viewer, p, { primary: index === 0, index, fadeInStart, cityLookup: cityLookupRef.current }),
            );
          });
          highlightsRef.current.push(...addConnectingArcs(viewer, points, fadeInStart));

          if (points.length === 1) {
            const { lat, lon } = points[0];
            viewer.camera.flyTo({
              destination: Cesium.Cartesian3.fromDegrees(lon, lat, SINGLE_HIGHLIGHT_ALTITUDE),
              orientation: { heading: 0, pitch: HIGHLIGHT_PITCH, roll: 0 },
              duration: 2.4,
              easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
            });
          } else {
            // Manual centroid framing — don't use viewer.flyTo(entities), the
            // animated sonar-ring radius confuses bounding-sphere math.
            // Stay at altitudes ≥ 12M so the whole Earth disk remains in frame.
            const lats = points.map((p) => p.lat);
            const lons = points.map((p) => p.lon);
            const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2;
            const centerLon = (Math.min(...lons) + Math.max(...lons)) / 2;
            const latSpread = Math.max(...lats) - Math.min(...lats);
            const lonSpread = Math.max(...lons) - Math.min(...lons);
            const maxSpread = Math.max(latSpread, lonSpread, 6);
            const altitude = Math.min(17_000_000, Math.max(12_000_000, 11_500_000 + maxSpread * 65_000));

            viewer.camera.flyTo({
              destination: Cesium.Cartesian3.fromDegrees(centerLon, centerLat, altitude),
              orientation: { heading: 0, pitch: HIGHLIGHT_PITCH, roll: 0 },
              duration: 2.4,
              easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
            });
          }
          break;
        }
        case 'overlay_badge': {
          const { lat, lon, text } = action.payload as {
            lat: number;
            lon: number;
            text: string;
          };
          viewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(lon, lat),
            label: {
              text: text.toUpperCase(),
              font: '500 11px "Inter", sans-serif',
              fillColor: color(GLOW, 0.95),
              outlineColor: color(MIDNIGHT, 0.95),
              outlineWidth: 3,
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              pixelOffset: new Cesium.Cartesian2(0, -18),
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            },
          });
          break;
        }
        case 'time_scrub_to':
        case 'none':
        default:
          break;
      }
    },
  }));

  return (
    <div className="absolute inset-0">
      {/* Cesium canvas — handles the Earth, stars, and atmosphere on its own now. */}
      <div ref={containerRef} className="absolute inset-0" />
    </div>
  );
});
