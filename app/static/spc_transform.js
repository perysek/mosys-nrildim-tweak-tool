/* ============================================================================
   spc_transform.js — client-side mirror of app/functions/spc.py transforms.

   Used for the 0.5s Preview animation (approximate, fast) on the SPC-Tweaks
   page. The authoritative computation still runs server-side at commit
   (spc.compute_tweaked_updates); this file must stay arithmetically identical to
   spc.py so preview == commit. A Node parity test (tests/test_js_parity...)
   asserts that equality. See IMPLEMENTATION-PLAN.md §3.3 / §3.3.1.

   Operates on the per-cavity row-average series (the same shape as
   spc.group_series output): { figura: { labels:[datetime...], values:[avg...] } }.
   Series are assumed already sorted chronologically by the server.
   ========================================================================== */
(function (global) {
    'use strict';

    var DEFAULT_PICK_THRESHOLD = 0.25;
    var FLATTEN_NUDGE = 0.10;
    var NB_EPS = 1e-9;

    function mean(arr) {
        if (!arr.length) return null;
        var s = 0;
        for (var i = 0; i < arr.length; i++) s += arr[i];
        return s / arr.length;
    }

    // Per-row flatten delta for one chronologically-ordered value array.
    function flattenDeltas(values, threshold, nominal) {
        var n = values.length;
        var deltas = new Array(n).fill(0.0);
        if (nominal === null || nominal === undefined) return deltas;
        for (var i = 1; i < n - 1; i++) {
            var v = values[i], left = values[i - 1], right = values[i + 1];
            if (v == null || left == null || right == null) continue;
            var nb = (left + right) / 2.0;
            if (Math.abs(nb) <= NB_EPS) continue;
            if (Math.abs(v - nb) / Math.abs(nb) <= threshold) continue;
            var flattened = (v <= nominal) ? nb * (1 - FLATTEN_NUDGE) : nb * (1 + FLATTEN_NUDGE);
            deltas[i] = flattened - v;
        }
        return deltas;
    }

    // Returns tweaked series in the same shape as the input.
    function tweakSeries(series, s, flatten, threshold, nominal) {
        if (threshold === undefined || threshold === null) threshold = DEFAULT_PICK_THRESHOLD;
        s = s || 0;
        var out = {};
        Object.keys(series).forEach(function (figura) {
            var labels = series[figura].labels;
            var values = series[figura].values.slice();
            var fdeltas = flatten ? flattenDeltas(values, threshold, nominal)
                                  : new Array(values.length).fill(0.0);
            var flattened = values.map(function (v, k) { return v + fdeltas[k]; });
            var mbar = (s && flattened.length) ? mean(flattened) : null;
            var newValues = values.map(function (v, k) {
                var sdelta = (mbar !== null && s) ? s * (mbar - flattened[k]) : 0.0;
                var total = fdeltas[k] + sdelta;
                return Math.round((v + total) * 1000) / 1000;
            });
            out[figura] = { labels: labels.slice(), values: newValues };
        });
        return out;
    }

    var api = {
        tweakSeries: tweakSeries,
        flattenDeltas: flattenDeltas,
        DEFAULT_PICK_THRESHOLD: DEFAULT_PICK_THRESHOLD,
        FLATTEN_NUDGE: FLATTEN_NUDGE
    };

    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else global.SPCTransform = api;
})(typeof window !== 'undefined' ? window : this);
