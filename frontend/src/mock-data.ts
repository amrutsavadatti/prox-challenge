import type { Artifact } from './types';

let artifactId = 1;
const aid = () => `artifact-${artifactId++}`;

interface MockResponse {
  text: string;
  artifacts?: Artifact[];
}

const responses: Array<{
  keywords: string[];
  response: MockResponse;
}> = [
  {
    keywords: ['wire', 'wiring', 'connect', 'connection', 'pin', 'pinout'],
    response: {
      text: 'Here\'s the wiring diagram for connecting the stepper motor to your controller board. Make sure to match the wire colors exactly — reversing A and B phases will cause the motor to vibrate instead of spinning smoothly.',
      artifacts: [
        {
          id: aid(),
          title: 'Stepper Motor Wiring',
          type: 'mermaid',
          content: `graph LR
    subgraph Controller["Controller Board"]
        A1["A+ (Red)"]
        A2["A- (Blue)"]
        B1["B+ (Green)"]
        B2["B- (Black)"]
        EN["ENABLE"]
        GND["GND"]
    end
    subgraph Motor["NEMA 17 Stepper"]
        MA["Coil A"]
        MB["Coil B"]
    end
    subgraph PSU["24V Power Supply"]
        VCC["V+ (24V)"]
        PGND["V- (GND)"]
    end
    A1 -->|"Red Wire"| MA
    A2 -->|"Blue Wire"| MA
    B1 -->|"Green Wire"| MB
    B2 -->|"Black Wire"| MB
    VCC -->|"Power"| Controller
    PGND -->|"Ground"| GND`,
        },
      ],
    },
  },
  {
    keywords: ['settings', 'configure', 'setup', 'calibrate', 'parameter'],
    response: {
      text: 'Here\'s an interactive settings panel for your print configuration. Adjust the values to see how they affect print quality and speed. The preview updates in real-time.',
      artifacts: [
        {
          id: aid(),
          title: '3D Print Settings',
          type: 'interactive',
          content: `<!DOCTYPE html>
<html>
<head>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 24px; }
  h2 { font-size: 18px; margin-bottom: 20px; color: #fff; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  .control { margin-bottom: 16px; }
  .control label { display: block; font-size: 13px; color: #9ca3af; margin-bottom: 6px; }
  .control input[type="range"] { width: 100%; accent-color: #c084fc; }
  .value { float: right; color: #c084fc; font-weight: 600; font-size: 13px; }
  .preview { background: #16213e; border-radius: 12px; padding: 20px; border: 1px solid #2a2a4a; }
  .bar { height: 8px; border-radius: 4px; margin: 8px 0; transition: all 0.3s ease; }
  .stat { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #2a2a4a; font-size: 14px; }
  .stat-value { color: #c084fc; font-weight: 600; }
  .warning { background: #422006; border: 1px solid #f59e0b; border-radius: 8px; padding: 12px; margin-top: 16px; font-size: 13px; color: #fbbf24; display: none; }
</style>
</head>
<body>
  <h2>Print Configuration</h2>
  <div class="grid">
    <div>
      <div class="control">
        <label>Layer Height <span class="value" id="lhVal">0.2mm</span></label>
        <input type="range" id="layerHeight" min="0.05" max="0.4" step="0.05" value="0.2" oninput="update()">
      </div>
      <div class="control">
        <label>Print Speed <span class="value" id="psVal">60mm/s</span></label>
        <input type="range" id="printSpeed" min="20" max="150" step="5" value="60" oninput="update()">
      </div>
      <div class="control">
        <label>Nozzle Temp <span class="value" id="ntVal">200°C</span></label>
        <input type="range" id="nozzleTemp" min="180" max="260" step="5" value="200" oninput="update()">
      </div>
      <div class="control">
        <label>Infill % <span class="value" id="ifVal">20%</span></label>
        <input type="range" id="infill" min="5" max="100" step="5" value="20" oninput="update()">
      </div>
    </div>
    <div class="preview">
      <h2>Estimated Results</h2>
      <div class="stat"><span>Print Time</span><span class="stat-value" id="time">2h 15m</span></div>
      <div class="stat"><span>Quality Score</span><span class="stat-value" id="quality">8/10</span></div>
      <div class="stat"><span>Material Used</span><span class="stat-value" id="material">45g</span></div>
      <div class="stat"><span>Strength</span><span class="stat-value" id="strength">Medium</span></div>
      <div class="bar" id="qualBar" style="background: linear-gradient(90deg, #c084fc 80%, #333 80%);"></div>
      <div id="warning" class="warning"></div>
    </div>
  </div>
  <script>
    function update() {
      const lh = parseFloat(document.getElementById('layerHeight').value);
      const ps = parseInt(document.getElementById('printSpeed').value);
      const nt = parseInt(document.getElementById('nozzleTemp').value);
      const inf = parseInt(document.getElementById('infill').value);
      document.getElementById('lhVal').textContent = lh + 'mm';
      document.getElementById('psVal').textContent = ps + 'mm/s';
      document.getElementById('ntVal').textContent = nt + '°C';
      document.getElementById('ifVal').textContent = inf + '%';
      const baseTime = 135;
      const timeMin = Math.round(baseTime * (0.2 / lh) * (60 / ps) * (1 + (inf - 20) * 0.01));
      const hours = Math.floor(timeMin / 60);
      const mins = timeMin % 60;
      document.getElementById('time').textContent = hours + 'h ' + mins + 'm';
      const qual = Math.min(10, Math.round(10 * (0.2 / lh) * Math.min(1, 80 / ps)));
      document.getElementById('quality').textContent = qual + '/10';
      document.getElementById('qualBar').style.background = 'linear-gradient(90deg, #c084fc ' + (qual * 10) + '%, #333 ' + (qual * 10) + '%)';
      const mat = Math.round(30 + inf * 0.7);
      document.getElementById('material').textContent = mat + 'g';
      const str = inf < 25 ? 'Low' : inf < 60 ? 'Medium' : 'High';
      document.getElementById('strength').textContent = str;
      const warn = document.getElementById('warning');
      if (ps > 100 && lh < 0.15) {
        warn.style.display = 'block';
        warn.textContent = '⚠ High speed with fine layers may cause quality issues. Consider reducing speed below 80mm/s for layers under 0.15mm.';
      } else if (nt > 240) {
        warn.style.display = 'block';
        warn.textContent = '⚠ Nozzle temperature above 240°C may cause stringing with PLA. Use PETG or ABS at this temperature.';
      } else {
        warn.style.display = 'none';
      }
    }
    update();
  </script>
</body>
</html>`,
        },
      ],
    },
  },
  {
    keywords: ['error', 'problem', 'issue', 'fail', 'not working', 'debug', 'fix', 'troubleshoot'],
    response: {
      text: 'Based on the symptoms you described, this looks like a common thermal runaway protection trigger. Here\'s a diagnostic checklist and the relevant error codes.',
      artifacts: [
        {
          id: aid(),
          title: 'Troubleshooting Guide',
          type: 'markdown',
          content: `# Thermal Runaway Diagnostic

## Common Causes

### 1. Loose Thermistor
The thermistor may have come loose from the heater block.

- **Check**: Gently wiggle the thermistor wires while monitoring temp readings
- **Fix**: Re-seat and secure with a small screw or thermal tape

### 2. Heater Cartridge Failure
| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Temp won't reach target | Failed cartridge | Replace heater |
| Temp fluctuates ±10°C | Loose connection | Re-crimp wires |
| Temp reads 0°C | Broken thermistor | Replace thermistor |

### 3. PID Tuning Required
Run auto-tune: \`M303 E0 S200 C8\`

Then save with: \`M500\`

## Error Codes
\`\`\`
ERR_THERMAL_01  - Heating too slow (check heater wattage)
ERR_THERMAL_02  - Temperature dropping during print
ERR_THERMAL_03  - Thermistor disconnected
ERR_THERMAL_04  - Temperature exceeded max (check thermistor type in firmware)
\`\`\`

> **Safety Note**: Never bypass thermal runaway protection. It exists to prevent fires.`,
        },
      ],
    },
  },
  {
    keywords: ['code', 'gcode', 'program', 'script', 'macro'],
    response: {
      text: 'Here\'s a G-code macro for the bed leveling sequence. This runs a 25-point mesh probe and stores the results.',
      artifacts: [
        {
          id: aid(),
          title: 'Bed Leveling Macro',
          type: 'code',
          language: 'gcode',
          content: `; === Auto Bed Leveling Macro ===
; For Marlin firmware with BLTouch/CRTouch

; Home all axes first
G28                  ; Home X, Y, Z

; Preheat bed for accurate measurement
M140 S60             ; Set bed temp to 60°C
M190 S60             ; Wait for bed to reach temp

; Set probe parameters
M851 Z-1.5           ; Set Z-probe offset (adjust for your setup)
G29 P1               ; Automated probing (25 points, 5x5 grid)

; Display mesh results
G29 T                ; Print topology report to console

; Activate bed leveling
G29 S1               ; Activate UBL
G29 F10.0            ; Set fade height (10mm)
G29 A                ; Activate mesh

; Save to EEPROM
M500                 ; Save settings
M501                 ; Load settings (verify)

; Report completion
M117 Bed leveling complete!

; Cool down
M140 S0              ; Turn off bed heater

; Return to home
G28 X Y              ; Home X and Y only`,
        },
      ],
    },
  },
  {
    keywords: ['weld', 'tig', 'amp', 'current', 'tungsten', 'gas', 'argon'],
    response: {
      text: 'Here are the recommended TIG welding parameters for your material. The interactive chart lets you adjust thickness to see how settings change.',
      artifacts: [
        {
          id: aid(),
          title: 'TIG Welding Parameters',
          type: 'interactive',
          content: `<!DOCTYPE html>
<html>
<head>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 24px; }
  h2 { color: #fff; margin-bottom: 16px; font-size: 18px; }
  .selector { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
  .selector button { padding: 8px 16px; border-radius: 8px; border: 1px solid #3a3a5a; background: #16213e; color: #e0e0e0; cursor: pointer; font-size: 14px; transition: all 0.2s; }
  .selector button.active { background: #c084fc; color: #1a1a2e; border-color: #c084fc; font-weight: 600; }
  .selector button:hover { border-color: #c084fc; }
  .param-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 20px; }
  .param { background: #16213e; border-radius: 10px; padding: 16px; border: 1px solid #2a2a4a; }
  .param-label { font-size: 12px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; }
  .param-value { font-size: 28px; font-weight: 700; color: #c084fc; margin: 4px 0; }
  .param-unit { font-size: 14px; color: #9ca3af; }
  .thickness-control { margin: 20px 0; }
  .thickness-control label { display: block; margin-bottom: 8px; font-size: 14px; }
  .thickness-control input { width: 100%; accent-color: #c084fc; }
  .tip { background: #1e3a5f; border-radius: 8px; padding: 12px; font-size: 13px; border-left: 3px solid #60a5fa; margin-top: 16px; }
</style>
</head>
<body>
  <h2>TIG Welding Settings Calculator</h2>
  <div class="selector" id="materials">
    <button class="active" onclick="setMaterial('steel')">Mild Steel</button>
    <button onclick="setMaterial('stainless')">Stainless Steel</button>
    <button onclick="setMaterial('aluminum')">Aluminum</button>
    <button onclick="setMaterial('titanium')">Titanium</button>
  </div>
  <div class="thickness-control">
    <label>Material Thickness: <strong id="thkVal">3.0mm</strong></label>
    <input type="range" id="thickness" min="0.5" max="10" step="0.5" value="3" oninput="update()">
  </div>
  <div class="param-grid">
    <div class="param"><div class="param-label">Amperage</div><div class="param-value" id="amps">95</div><div class="param-unit">Amps (DCEN)</div></div>
    <div class="param"><div class="param-label">Gas Flow</div><div class="param-value" id="gas">15</div><div class="param-unit">CFH Argon</div></div>
    <div class="param"><div class="param-label">Tungsten</div><div class="param-value" id="tungsten">2.4</div><div class="param-unit">mm (2% Lanthanated)</div></div>
    <div class="param"><div class="param-label">Filler Rod</div><div class="param-value" id="filler">2.4</div><div class="param-unit" id="fillerType">mm ER70S-2</div></div>
  </div>
  <div class="tip" id="tip">For steel at this thickness, use a slight weave pattern. Keep the tungsten 3-5mm from the workpiece.</div>
  <script>
    let material = 'steel';
    const data = {
      steel:     { ampBase: 30, ampPer: 22, gasMin: 12, gasMax: 25, tungsten: [1.6,1.6,2.4,2.4,3.2], filler: 'ER70S-2', polarity: 'DCEN', tips: ['Use a slight weave pattern.','Keep tungsten 3-5mm from workpiece.','Use 2% lanthanated tungsten (gold band).'] },
      stainless: { ampBase: 25, ampPer: 20, gasMin: 12, gasMax: 20, tungsten: [1.6,1.6,2.4,2.4,3.2], filler: 'ER308L', polarity: 'DCEN', tips: ['Minimize heat input to prevent warping.','Use a gas lens for better coverage.','Back-purge with argon to prevent sugaring.'] },
      aluminum:  { ampBase: 35, ampPer: 25, gasMin: 15, gasMax: 30, tungsten: [1.6,2.4,2.4,3.2,3.2], filler: 'ER4043', polarity: 'AC', tips: ['Use AC with 70% electrode negative balance.','Clean oxide layer with stainless brush before welding.','Use a larger cup (size 8-12) for better gas coverage.'] },
      titanium:  { ampBase: 20, ampPer: 18, gasMin: 20, gasMax: 35, tungsten: [1.6,1.6,2.4,2.4,3.2], filler: 'ERTi-2', polarity: 'DCEN', tips: ['Full argon shielding is critical — use trailing shield.','Weld must be silver/gold colored, never blue/gray.','Allow slow cooling under argon gas.'] },
    };
    function setMaterial(m) {
      material = m;
      document.querySelectorAll('.selector button').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');
      update();
    }
    function update() {
      const t = parseFloat(document.getElementById('thickness').value);
      const d = data[material];
      document.getElementById('thkVal').textContent = t.toFixed(1) + 'mm';
      const amps = Math.round(d.ampBase + t * d.ampPer);
      document.getElementById('amps').textContent = amps;
      document.querySelector('#amps + .param-unit').textContent = 'Amps (' + d.polarity + ')';
      const gas = Math.round(d.gasMin + (t / 10) * (d.gasMax - d.gasMin));
      document.getElementById('gas').textContent = gas;
      const ti = Math.min(Math.floor(t / 2), d.tungsten.length - 1);
      document.getElementById('tungsten').textContent = d.tungsten[ti];
      const fillerSize = d.tungsten[ti];
      document.getElementById('filler').textContent = fillerSize;
      document.getElementById('fillerType').textContent = 'mm ' + d.filler;
      const tipIdx = Math.floor(Math.random() * d.tips.length);
      document.getElementById('tip').textContent = d.tips[tipIdx] + ' Keep the tungsten ' + Math.round(2 + t) + '-' + Math.round(4 + t) + 'mm from the workpiece.';
    }
    update();
  </script>
</body>
</html>`,
        },
      ],
    },
  },
  {
    keywords: ['table', 'compare', 'spec', 'specification', 'material', 'data'],
    response: {
      text: 'Here\'s a comparison table of common filament materials with their key properties. This should help you pick the right material for your application.',
      artifacts: [
        {
          id: aid(),
          title: 'Filament Comparison',
          type: 'table',
          content: JSON.stringify({
            headers: ['Material', 'Print Temp', 'Bed Temp', 'Strength', 'Flexibility', 'Ease of Print', 'Best For'],
            rows: [
              ['PLA', '190-220°C', '0-60°C', 'Medium', 'Low', 'Easy', 'Prototypes, decorative'],
              ['PETG', '220-250°C', '70-80°C', 'High', 'Medium', 'Moderate', 'Functional parts, outdoor'],
              ['ABS', '230-260°C', '100-110°C', 'High', 'Medium', 'Hard', 'Mechanical parts, enclosures'],
              ['TPU', '210-230°C', '0-60°C', 'Medium', 'Very High', 'Hard', 'Flexible parts, gaskets'],
              ['Nylon', '240-270°C', '70-90°C', 'Very High', 'High', 'Hard', 'Gears, bearings, tools'],
              ['ASA', '240-260°C', '90-110°C', 'High', 'Medium', 'Moderate', 'Outdoor, UV-resistant parts'],
            ],
          }),
        },
      ],
    },
  },
  {
    keywords: ['json', 'config', 'firmware', 'configuration'],
    response: {
      text: 'Here\'s the firmware configuration for your board. You can review the key parameters — I\'ve highlighted the ones most commonly needing adjustment.',
      artifacts: [
        {
          id: aid(),
          title: 'Firmware Config',
          type: 'json',
          content: JSON.stringify({
            firmware: { version: '2.1.2', board: 'BTT SKR Mini E3 V3.0' },
            motion: {
              steps_per_mm: { x: 80, y: 80, z: 400, e: 93 },
              max_feedrate: { x: 300, y: 300, z: 5, e: 25 },
              max_acceleration: { x: 3000, y: 3000, z: 100, e: 10000 },
              jerk: { x: 10, y: 10, z: 0.3, e: 5 },
            },
            temperature: {
              hotend: { max: 275, pid: { p: 22.2, i: 1.08, d: 114.0 } },
              bed: { max: 120, pid: { p: 97.1, i: 1.41, d: 1675.16 } },
            },
            features: {
              auto_bed_leveling: 'bilinear',
              probe_type: 'BLTouch',
              filament_runout: true,
              power_loss_recovery: true,
            },
          }, null, 2),
        },
      ],
    },
  },
];

const defaultResponse: MockResponse = {
  text: 'I can help you with that! Could you provide more details about what specific aspect you need assistance with? For example, I can help with:\n\n- **Wiring & connections** — pinout diagrams, motor wiring\n- **Settings & calibration** — temperature, speed, material parameters\n- **Troubleshooting** — error codes, diagnostic procedures\n- **G-code & macros** — custom commands, automated sequences\n- **Material selection** — comparison charts, recommended settings\n\nJust describe your situation and I\'ll provide visual guides and interactive tools to help.',
};

export function generateMockResponse(input: string): MockResponse {
  const lower = input.toLowerCase();
  for (const r of responses) {
    if (r.keywords.some((kw) => lower.includes(kw))) {
      // Return with fresh artifact IDs
      return {
        text: r.response.text,
        artifacts: r.response.artifacts?.map((a) => ({ ...a, id: aid() })),
      };
    }
  }
  return defaultResponse;
}
