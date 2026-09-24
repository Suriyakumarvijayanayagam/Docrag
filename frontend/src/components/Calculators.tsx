import { useEffect, useState } from 'react'
import { api } from '../api'

type Result = { formula: string | Record<string, string>; reference: string; warnings: string[]; [key: string]: unknown }

const PROCESSES = [
  ['SMAW', 'SMAW (MMA, stick)'], ['GMAW', 'GMAW (MIG/MAG)'], ['FCAW', 'FCAW (flux-cored)'], ['MCAW', 'MCAW (metal-cored)'],
  ['SAW', 'SAW (submerged arc)'], ['GTAW', 'GTAW (TIG)'], ['PAW', 'PAW (plasma)'],
] as const

/** Posts the inputs whenever they change (debounced) and keeps the latest result or error. */
function useCalculation(path: string, inputs: Record<string, string>) {
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState('')
  const key = JSON.stringify(inputs)
  useEffect(() => {
    const values = Object.fromEntries(Object.entries(inputs).map(([name, value]) => [name, name === 'process' ? value : Number(value)]))
    if (Object.entries(values).some(([name, value]) => name !== 'process' && (inputs[name].trim() === '' || !Number.isFinite(value)))) {
      setResult(null)
      setError('')
      return
    }
    let alive = true
    const timer = window.setTimeout(() => {
      api<Result>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) })
        .then(data => { if (alive) { setResult(data); setError('') } })
        .catch(reason => { if (alive) { setResult(null); setError(reason instanceof Error ? reason.message : 'Could not calculate') } })
    }, 250)
    return () => { alive = false; window.clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key])
  return { result, error }
}

function NumberField({ label, unit, value, onChange, step = 'any' }: { label: string; unit?: string; value: string; onChange: (value: string) => void; step?: string }) {
  return <label className="calc-field">
    <span>{label}</span>
    <span className="calc-input"><input type="number" inputMode="decimal" step={step} min="0" value={value} onChange={event => onChange(event.target.value)} />{unit && <em>{unit}</em>}</span>
  </label>
}

function Footnotes({ result, error }: { result: Result | null; error: string }) {
  if (error) return <p className="calc-error">{error}</p>
  if (!result) return null
  const labels: Record<string, string> = { ce_iiw: 'CE (IIW)', cet: 'CET', pcm: 'Pcm' }
  const formulas = typeof result.formula === 'string' ? [result.formula] : Object.entries(result.formula).map(([key, formula]) => `${labels[key] ?? key} = ${formula}`)
  return <div className="calc-notes">
    {result.warnings.length > 0 && <ul className="calc-warnings">{result.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>}
    {formulas.map(formula => <code key={formula}>{formula}</code>)}
    <p>{result.reference}</p>
  </div>
}

function HeatInput({ onHeatInput }: { onHeatInput: (value: number) => void }) {
  const [inputs, setInputs] = useState({ voltage: '24', current: '160', travel_speed_mm_min: '150', process: 'SMAW' })
  const set = (name: keyof typeof inputs) => (value: string) => setInputs(current => ({ ...current, [name]: value }))
  const { result, error } = useCalculation('/calc/heat-input', inputs)
  return <section className="panel calc">
    <header className="panel-header"><div><h2>Heat input</h2><p>Arc energy and heat input per unit length of weld.</p></div></header>
    <div className="calc-body">
      <div className="calc-fields">
        <label className="calc-field"><span>Process</span><select className="select" value={inputs.process} onChange={event => set('process')(event.target.value)}>{PROCESSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <NumberField label="Voltage" unit="V" value={inputs.voltage} onChange={set('voltage')} />
        <NumberField label="Current" unit="A" value={inputs.current} onChange={set('current')} />
        <NumberField label="Travel speed" unit="mm/min" value={inputs.travel_speed_mm_min} onChange={set('travel_speed_mm_min')} />
      </div>
      {result && <dl className="calc-results">
        <div><dt>Arc energy</dt><dd>{String(result.arc_energy_kj_mm)}<small>kJ/mm</small></dd></div>
        <div><dt>Heat input (k = {String(result.efficiency)})</dt><dd>{String(result.heat_input_kj_mm)}<small>kJ/mm</small></dd></div>
      </dl>}
      {result && <button className="btn btn-sm calc-use" onClick={() => onHeatInput(Number(result.heat_input_kj_mm))}>Use in preheat</button>}
    </div>
    <Footnotes result={result} error={error} />
  </section>
}

const ELEMENTS = ['C', 'Mn', 'Si', 'Cr', 'Mo', 'V', 'Ni', 'Cu', 'B'] as const

function CarbonEquivalent({ onCet }: { onCet: (value: number) => void }) {
  const [inputs, setInputs] = useState<Record<string, string>>({ C: '0.18', Mn: '1.40', Si: '0.30', Cr: '0', Mo: '0', V: '0', Ni: '0', Cu: '0', B: '0' })
  const { result, error } = useCalculation('/calc/carbon-equivalent', inputs)
  return <section className="panel calc">
    <header className="panel-header"><div><h2>Carbon equivalent</h2><p>From the mill certificate composition, in weight %.</p></div></header>
    <div className="calc-body">
      <div className="calc-fields elements">
        {ELEMENTS.map(element => <NumberField key={element} label={element} unit="%" value={inputs[element]} onChange={value => setInputs(current => ({ ...current, [element]: value }))} />)}
      </div>
      {result && <dl className="calc-results">
        <div><dt>CE (IIW)</dt><dd>{String(result.ce_iiw)}</dd></div>
        <div><dt>CET</dt><dd>{String(result.cet)}</dd></div>
        <div><dt>Pcm</dt><dd>{String(result.pcm)}</dd></div>
      </dl>}
      {result && <button className="btn btn-sm calc-use" onClick={() => onCet(Number(result.cet))}>Use CET in preheat</button>}
    </div>
    <Footnotes result={result} error={error} />
  </section>
}

function Preheat({ inputs, setInputs }: { inputs: Record<string, string>; setInputs: (change: (current: Record<string, string>) => Record<string, string>) => void }) {
  const { result, error } = useCalculation('/calc/preheat', inputs)
  const set = (name: string) => (value: string) => setInputs(current => ({ ...current, [name]: value }))
  return <section className="panel calc">
    <header className="panel-header"><div><h2>Preheat estimate</h2><p>Minimum preheat to avoid hydrogen cracking, by the CET method.</p></div></header>
    <div className="calc-body">
      <div className="calc-fields">
        <NumberField label="CET" unit="%" value={inputs.cet} onChange={set('cet')} />
        <NumberField label="Plate thickness" unit="mm" value={inputs.thickness_mm} onChange={set('thickness_mm')} />
        <NumberField label="Diffusible hydrogen" unit="ml/100 g" value={inputs.hydrogen_ml_100g} onChange={set('hydrogen_ml_100g')} />
        <NumberField label="Heat input" unit="kJ/mm" value={inputs.heat_input_kj_mm} onChange={set('heat_input_kj_mm')} />
      </div>
      {result && <dl className="calc-results">
        <div><dt>Minimum preheat</dt><dd>{result.required ? <>{String(result.preheat_c)}<small>°C</small></> : <span className="calc-none">Not required</span>}</dd></div>
        {!result.required && <div><dt>Formula result</dt><dd>{String(result.preheat_c)}<small>°C</small></dd></div>}
      </dl>}
    </div>
    <Footnotes result={result} error={error} />
  </section>
}

export function Calculators() {
  const [preheat, setPreheat] = useState<Record<string, string>>({ cet: '0.35', thickness_mm: '25', hydrogen_ml_100g: '5', heat_input_kj_mm: '1.5' })
  return <div className="calc-page">
    <p className="calc-intro">Computed exactly, not by the model. Results are estimates to check against the governing code and your qualified WPS.</p>
    <div className="calc-grid">
      <HeatInput onHeatInput={value => setPreheat(current => ({ ...current, heat_input_kj_mm: String(value) }))} />
      <CarbonEquivalent onCet={value => setPreheat(current => ({ ...current, cet: String(value) }))} />
      <Preheat inputs={preheat} setInputs={setPreheat} />
    </div>
  </div>
}
