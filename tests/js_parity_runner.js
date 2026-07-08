/* Node runner for the JS<->Python transform parity test.
   Reads {series, s, flatten, threshold, nominal} as JSON on stdin, runs the
   real app/static/spc_transform.js tweakSeries, writes the result as JSON. */
const path = require('path');
const SPC = require(path.join(__dirname, '..', 'app', 'static', 'spc_transform.js'));

let input = '';
process.stdin.on('data', function (d) { input += d; });
process.stdin.on('end', function () {
    const cfg = JSON.parse(input);
    const out = SPC.tweakSeries(cfg.series, cfg.s, cfg.shift, cfg.flatten, cfg.threshold, cfg.nominal);
    process.stdout.write(JSON.stringify(out));
});
