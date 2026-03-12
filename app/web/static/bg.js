/**
 * Speaker HASS — Lightweight WebGL background shader
 * Soft flowing gradient, ~60fps on RPi 5 Chromium
 */

(function () {
    "use strict";

    // Create canvas dynamically to avoid layout interference
    var canvas = document.createElement("canvas");
    canvas.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;display:block;";
    document.body.insertBefore(canvas, document.body.firstChild);

    var gl = canvas.getContext("webgl", { alpha: false, antialias: false, depth: false, stencil: false });
    if (!gl) { canvas.remove(); return; }

    // State color targets (RGB 0-1)
    var stateColors = {
        idle:       [0.00, 0.44, 0.89],
        wake:       [0.19, 0.82, 0.35],
        listening:  [0.19, 0.82, 0.35],
        processing: [1.00, 0.62, 0.04],
        responding: [0.75, 0.35, 0.95],
        error:      [1.00, 0.27, 0.23],
    };

    var currentColor = stateColors.idle.slice();
    var targetColor = stateColors.idle.slice();
    var currentState = "idle";

    window.setBgState = function (state) {
        currentState = state;
        var c = stateColors[state];
        if (c) {
            targetColor[0] = c[0];
            targetColor[1] = c[1];
            targetColor[2] = c[2];
        }
    };

    var vsrc = [
        "attribute vec2 a_pos;",
        "void main(){gl_Position=vec4(a_pos,0.0,1.0);}"
    ].join("\n");

    var fsrc = [
        "precision mediump float;",
        "uniform float u_time;",
        "uniform vec2 u_res;",
        "uniform vec3 u_color;",
        "uniform float u_dark;",
        "",
        "void main(){",
        "  vec2 uv=gl_FragCoord.xy/u_res;",
        "  float t=u_time*0.15;",
        "",
        "  // Two slow sine waves for gentle motion",
        "  float w1=sin(uv.x*2.5+t)*sin(uv.y*2.0-t*0.7)*0.5+0.5;",
        "  float w2=sin(uv.x*1.8-t*0.6+1.0)*sin(uv.y*3.0+t*0.4)*0.5+0.5;",
        "  float w=mix(w1,w2,0.5);",
        "",
        "  // Subtle vertical gradient",
        "  float grad=1.0-uv.y*0.3;",
        "",
        "  // Mix accent color at very low intensity for a hint of life",
        "  float intensity=w*0.07*grad;",
        "  vec3 bg=mix(vec3(1.0),vec3(0.0),u_dark);",
        "  vec3 col=bg+u_color*intensity*(1.0-u_dark*0.5);",
        "",
        "  // Darken slightly in dark mode",
        "  col=mix(col,col*0.85,u_dark);",
        "",
        "  gl_FragColor=vec4(col,1.0);",
        "}"
    ].join("\n");

    function compile(type, src) {
        var s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        return s;
    }

    var prog = gl.createProgram();
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, vsrc));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, fsrc));
    gl.linkProgram(prog);
    gl.useProgram(prog);

    // Full-screen quad
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    var aPos = gl.getAttribLocation(prog, "a_pos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    var uTime = gl.getUniformLocation(prog, "u_time");
    var uRes = gl.getUniformLocation(prog, "u_res");
    var uColor = gl.getUniformLocation(prog, "u_color");
    var uDark = gl.getUniformLocation(prog, "u_dark");

    function isDark() {
        return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? 1.0 : 0.0;
    }

    var w = 0, h = 0;
    function resize() {
        var dpr = Math.min(window.devicePixelRatio || 1, 1.5); // Cap DPR for perf
        var nw = window.innerWidth * dpr | 0;
        var nh = window.innerHeight * dpr | 0;
        if (w !== nw || h !== nh) {
            w = nw;
            h = nh;
            canvas.width = w;
            canvas.height = h;
            gl.viewport(0, 0, w, h);
        }
    }

    var startTime = performance.now();

    function frame() {
        resize();

        // Smooth color interpolation
        var lerp = 0.03;
        currentColor[0] += (targetColor[0] - currentColor[0]) * lerp;
        currentColor[1] += (targetColor[1] - currentColor[1]) * lerp;
        currentColor[2] += (targetColor[2] - currentColor[2]) * lerp;

        var t = (performance.now() - startTime) * 0.001;
        gl.uniform1f(uTime, t);
        gl.uniform2f(uRes, w, h);
        gl.uniform3f(uColor, currentColor[0], currentColor[1], currentColor[2]);
        gl.uniform1f(uDark, isDark());
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

        requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
})();
