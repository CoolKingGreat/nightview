import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

const ease = [0.16, 1, 0.3, 1] as const;

interface Props {
  open: boolean;
  onClose: () => void;
}

export function Methodology({ open, onClose }: Props) {
  const [measuredCount, setMeasuredCount] = useState<number | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const ds = d?.data_source;
        if (!ds) return;
        if (typeof ds.measured === 'number') setMeasuredCount(ds.measured);
        if (typeof ds.row_count === 'number') setTotalCount(ds.row_count);
      })
      .catch(() => {
        // /api/health is optional here; if it fails the page just omits the live counts.
      });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="methodology"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.45, ease }}
          className="fixed inset-0 z-[60] grid place-items-center bg-black/70 backdrop-blur-[6px]"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.55, ease, delay: 0.05 }}
            onClick={(e) => e.stopPropagation()}
            className="relative mx-4 max-h-[88vh] w-full max-w-[760px] overflow-hidden rounded-[20px] border border-white/[0.07] bg-[#080B12]/95 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.85)] backdrop-blur-xl"
          >
            <button
              type="button"
              onClick={onClose}
              aria-label="close"
              className="absolute right-4 top-4 z-10 grid h-8 w-8 place-items-center rounded-full border border-white/[0.1] bg-[#0A0D17]/85 font-mono text-[12px] text-ink/80 backdrop-blur transition-colors hover:border-glow/40 hover:text-glow"
            >
              ✕
            </button>

            <div className="max-h-[88vh] overflow-y-auto px-8 py-10 md:px-12 md:py-12">
              <div className="font-mono text-[9px] uppercase tracking-[0.32em] text-glow/75">
                methodology
              </div>
              <h1 className="mt-3 font-display text-[1.8rem] font-semibold leading-tight text-ink">
                How Nightview knows what it knows.
              </h1>

              <Section title="The data">
                <p>
                  The night-sky brightness numbers come from NASA&apos;s VIIRS Day/Night Band,
                  specifically the VNP46A2 Black Marble product. This is the same satellite imagery
                  NASA uses for its &ldquo;Earth at Night&rdquo; maps. The instrument lives on the
                  Suomi NPP and NOAA-20 satellites and observes nightly. Useful science data starts
                  in April 2012 and now spans roughly 156 months.
                </p>
                <p>
                  Each city is measured as the median radiance over a 10 km radius around its
                  centroid, in monthly composites. Daily pixels are filtered to the
                  BRDF-corrected, lunar-and-cloud-corrected good-quality observations using
                  VIIRS&apos;s own quality flag (<Code>Mandatory_Quality_Flag = 0</Code>). All of
                  this aggregation happens server-side on Google Earth Engine in one call per
                  city.
                </p>
                <p>
                  The dataset carries{' '}
                  {totalCount != null ? <Strong>{totalCount.toLocaleString()}</Strong> : 'roughly 2,940'}{' '}
                  cities and dark-sky destinations.{' '}
                  {measuredCount != null ? (
                    <>
                      Of these, <Strong>{measuredCount.toLocaleString()}</Strong> carry the tag{' '}
                      <Code>data_source: &quot;measured&quot;</Code>, meaning their numbers come
                      directly from VIIRS pixels.
                    </>
                  ) : (
                    <>
                      A subset carry the tag <Code>data_source: &quot;measured&quot;</Code>,
                      meaning their numbers come directly from VIIRS pixels.
                    </>
                  )}{' '}
                  The remainder carry <Code>data_source: &quot;modeled&quot;</Code>: their
                  baseline radiance is a heuristic of city population, their trend is the
                  published country-level rate from Kyba (2017) and S&aacute;nchez de Miguel
                  (2021), and their monthly time series is a smooth exponential fit. The Inspector
                  and the conversational agent both surface this tag so you always know which is
                  which.
                </p>
              </Section>

              <Section title="VIIRS radiance to sky-quality magnitude">
                <p>
                  VIIRS reports radiance in nanowatts per square centimeter per steradian (nW/cm
                  &sup2;/sr). Stargazers and dark-sky surveys use a different unit: SQM, sky
                  brightness in magnitudes per square arcsecond, where larger numbers are darker.
                  The conversion follows Falchi et&nbsp;al. (2016), the published World Atlas of
                  Artificial Night Sky Brightness:
                </p>
                <Formula>SQM = 22.0 - 2.5 * log10(radiance / 0.171 + 1)</Formula>
                <p>
                  22.0 is the SQM of a pristine sky; 0.171 nW is the natural-night reference
                  (airglow plus zodiacal light). For Cherry Springs State Park, the measured
                  radiance is about 0.02 nW, giving SQM &asymp; 21.9. For Houston the measured
                  radiance is about 72 nW, giving SQM &asymp; 15.4.
                </p>
              </Section>

              <Section title="SQM to Bortle class">
                <p>
                  The Bortle scale is John Bortle&apos;s 9-step classification of night-sky
                  quality, published in Sky &amp; Telescope in 2001. Class 1 is pristine
                  dark-sky (SQM &ge; 21.99); Class 9 is inner-city (SQM &lt; 17.80); the rest fall
                  between. The class drives the &ldquo;you can see&rdquo; content in the
                  Inspector: typical star counts, Milky Way appearance, and the list of
                  naked-eye objects (Andromeda, the Orion Nebula, the Pleiades, zodiacal
                  light) that are realistically observable at that level of light pollution.
                </p>
              </Section>

              <Section title="SQM to naked-eye limiting magnitude">
                <p>
                  The faintest star visible at zenith (NELM) relates to SQM via a published
                  interpolation table. We use Crumey (2014) reference points with linear
                  interpolation. At Cherry Springs&apos;s SQM 21.9, NELM &asymp; 7.6: any star
                  brighter than magnitude 7.6 is within naked-eye reach. At Houston&apos;s SQM
                  15.4, NELM is about 2.5: only the brightest dozen or so stars cut through.
                </p>
              </Section>

              <Section title="Forecasts">
                <p>
                  Forecasts run 120 months ahead using Prophet, Facebook&apos;s open-source
                  time-series library, trained on each measured city&apos;s monthly radiance
                  series with yearly seasonality enabled and a linear growth model. We
                  don&apos;t tune per city; Prophet&apos;s defaults handle the slow,
                  near-monotonic VIIRS trends well. The forecast feeds the year scrubber and
                  the agent&apos;s answers about future brightness.
                </p>
                <p>
                  For modeled cities (no measured monthly series), the forecast is just
                  compound extrapolation of the modeled trend. Honest, but not really a
                  forecast in the statistical sense.
                </p>
              </Section>

              <Section title="What this dataset is honest about">
                <Ul>
                  <li>
                    The 10 km buffer averages in a lot of water for coastal cities. San
                    Francisco at the centroid catches the Pacific; Hong Kong catches the Pearl
                    Estuary; Sydney catches the harbor. The numbers are real for that buffer
                    but they understate the urban core.
                  </li>
                  <li>
                    VIIRS DNB has a noise floor near the dark end. Truly pristine sites cluster
                    around SQM 21.5 to 22, even when the actual sky is slightly darker.
                  </li>
                  <li>
                    Modeled cities use country-level trend averages from published research.
                    Useful as a directional signal, but a city mid-LED-transition (Chicago is
                    the canonical case) will look like it&apos;s brightening at the country
                    average until per-pixel measurement is added. The agent hedges with
                    &ldquo;around&rdquo; and &ldquo;roughly&rdquo; for modeled cities and cites
                    measured cities precisely.
                  </li>
                  <li>
                    Forecasts assume the past 13 years of trend continue. A city mid-LED
                    rollout may flatten or reverse beyond the 10-year horizon in ways Prophet
                    can&apos;t anticipate.
                  </li>
                </Ul>
              </Section>

              <Section title="The agent">
                <p>
                  The conversational agent (Claude Haiku 4.5, escalating to Sonnet 4.6 on
                  comparative queries) gets the full data record for every place it queries:
                  measured or modeled, radiance, SQM, Bortle class, trend, milestone years,
                  forecast confidence, and the nearest dark-sky destination. Its system prompt
                  instructs it to cite precise numbers when the source is measured and to
                  hedge when modeled, to lead with the named visible objects when asked
                  &ldquo;what can I see from here,&rdquo; and to surface the nearest reachable
                  dark sky when the Milky Way isn&apos;t visible locally.
                </p>
              </Section>

              <Section title="References">
                <Ul>
                  <li>
                    Falchi et&nbsp;al. (2016). The new world atlas of artificial night sky
                    brightness. <em>Science Advances</em> 2(6).
                  </li>
                  <li>
                    Bortle, J. (2001). Introducing the Bortle Dark-Sky Scale.{' '}
                    <em>Sky &amp; Telescope</em>, February.
                  </li>
                  <li>
                    Kyba et&nbsp;al. (2017). Artificially lit surface of Earth at night
                    increasing in radiance and extent. <em>Science Advances</em> 3(11).
                  </li>
                  <li>
                    S&aacute;nchez de Miguel et&nbsp;al. (2021). First estimation of global
                    trends in nocturnal power emissions. <em>Remote Sensing</em> 13(16).
                  </li>
                  <li>
                    Crumey, A. (2014). Human contrast threshold and astronomical visibility.{' '}
                    <em>Monthly Notices of the Royal Astronomical Society</em> 442(3).
                  </li>
                  <li>
                    NASA Black Marble product (VNP46A2):{' '}
                    <Link href="https://blackmarble.gsfc.nasa.gov">blackmarble.gsfc.nasa.gov</Link>
                  </li>
                  <li>
                    International Dark-Sky Places:{' '}
                    <Link href="https://darksky.org">darksky.org</Link>
                  </li>
                </Ul>
              </Section>

              <div className="mt-12 border-t border-white/[0.05] pt-6 font-mono text-[10px] uppercase leading-relaxed tracking-[0.28em] text-muted/80">
                built by aryan valsa pradeep
                <br />
                source on{' '}
                <Link href="https://github.com/CoolKingGreat/nightview">github</Link> &middot;{' '}
                fastapi + claude + cesiumjs + geoai
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-9">
      <h2 className="font-display text-[1.05rem] font-semibold tracking-tight text-ink/95">
        {title}
      </h2>
      <div className="mt-3 space-y-3 font-body text-[14px] leading-[1.7] text-ink/78">
        {children}
      </div>
    </section>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded border border-white/[0.07] bg-white/[0.04] px-1.5 py-[1px] font-mono text-[12.5px] text-ink/90">
      {children}
    </code>
  );
}

function Strong({ children }: { children: React.ReactNode }) {
  return <strong className="font-semibold text-ink/95">{children}</strong>;
}

function Formula({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-4 rounded-lg border border-white/[0.07] bg-white/[0.03] px-4 py-3 font-mono text-[13px] text-glow/90">
      {children}
    </div>
  );
}

function Ul({ children }: { children: React.ReactNode }) {
  return <ul className="space-y-2 pl-1">{children}</ul>;
}

function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-glow/90 underline decoration-glow/30 underline-offset-2 transition-colors hover:text-glow"
    >
      {children}
    </a>
  );
}
