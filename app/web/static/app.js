/**
 * Speaker HASS — WebSocket client & UI controller
 */

(function () {
    "use strict";

    const orb = document.getElementById("orb");
    const stateLabel = document.getElementById("stateLabel");
    const stateDetail = document.getElementById("stateDetail");
    const transcriptCurrent = document.getElementById("transcriptCurrent");
    const historyList = document.getElementById("historyList");
    const historySection = document.getElementById("historySection");
    const connectionDot = document.querySelector(".connection-dot");
    const connectionText = document.querySelector(".connection-text");

    let ws = null;
    let reconnectDelay = 1000;
    let currentState = "idle";

    const stateDetails = {
        idle: "Waiting for wake word",
        wake: "Wake word detected",
        listening: "Listening to your voice",
        processing: "Thinking…",
        responding: "Speaking response",
        error: "Connection lost",
    };

    function connect() {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(`${protocol}//${location.host}/ws`);

        ws.onopen = function () {
            reconnectDelay = 1000;
            setConnection("connected");
        };

        ws.onclose = function () {
            setConnection("disconnected");
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 1.5, 10000);
        };

        ws.onerror = function () {
            ws.close();
        };

        ws.onmessage = function (event) {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        };
    }

    function handleMessage(msg) {
        switch (msg.type) {
            case "init":
                setState(msg.state.state, msg.state.label);
                if (msg.transcript) {
                    showTranscript(msg.transcript);
                }
                if (msg.history && msg.history.length > 0) {
                    msg.history.reverse().forEach(function (entry) {
                        addHistoryItem(entry.text);
                    });
                }
                setConnection(msg.state.connected ? "connected" : "ha-disconnected");
                break;

            case "state":
                setState(msg.state, msg.label);
                if (msg.connected !== undefined) {
                    setConnection(msg.connected ? "connected" : "ha-disconnected");
                }
                break;

            case "transcript":
                showTranscript(msg.text);
                addHistoryItem(msg.text);
                break;

            case "announcement":
                showTranscript(msg.text);
                addHistoryItem("\u{1F4E2} " + msg.text);
                break;

            case "wakeword":
                // Visual feedback handled by state change
                break;
        }
    }

    function setState(state, label) {
        currentState = state;

        // Update orb
        orb.className = "orb state-" + state;

        // Update text
        stateLabel.textContent = label || state.charAt(0).toUpperCase() + state.slice(1);
        stateDetail.textContent = stateDetails[state] || "";

        // Clear transcript display when going idle
        if (state === "idle") {
            setTimeout(function () {
                if (currentState === "idle") {
                    transcriptCurrent.classList.remove("visible");
                }
            }, 3000);
        }

        // Hide transcript for listening state
        if (state === "listening" || state === "wake") {
            transcriptCurrent.classList.remove("visible");
        }

        // Notify shader of state change
        if (window.setBgState) window.setBgState(state);
    }

    function showTranscript(text) {
        transcriptCurrent.textContent = '"' + text + '"';
        transcriptCurrent.classList.add("visible");
    }

    function addHistoryItem(text) {
        if (!text) return;
        const li = document.createElement("li");
        li.textContent = text;
        historyList.insertBefore(li, historyList.firstChild);

        // Keep only last 10
        while (historyList.children.length > 10) {
            historyList.removeChild(historyList.lastChild);
        }

        historySection.style.display = "block";
    }

    function setConnection(status) {
        connectionDot.className = "connection-dot";
        switch (status) {
            case "connected":
                connectionDot.classList.add("connected");
                connectionText.textContent = "Connected";
                break;
            case "ha-disconnected":
                connectionDot.classList.add("error");
                connectionText.textContent = "HA Disconnected";
                break;
            default:
                connectionText.textContent = "Reconnecting…";
                break;
        }
    }

    // Orb click: trigger wake word (idle) or stop listening (listening)
    orb.addEventListener("click", function () {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        if (currentState === "idle") {
            ws.send(JSON.stringify({ type: "trigger" }));
        } else if (currentState === "listening") {
            ws.send(JSON.stringify({ type: "stop_listening" }));
        }
    });

    // ---- Volume Control ----
    const volumeControl = document.getElementById("volumeControl");
    const volumeBtn = document.getElementById("volumeBtn");
    const volumeSlider = document.getElementById("volumeSlider");
    let volumeDebounce = null;

    // Load initial volume
    fetch("/api/volume")
        .then(function (r) { return r.json(); })
        .then(function (d) { volumeSlider.value = d.volume; updateVolumeIcon(d.volume); })
        .catch(function () {});

    // Toggle slider visibility
    volumeBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        volumeControl.classList.toggle("open");
    });

    // Close slider when tapping elsewhere
    document.addEventListener("click", function (e) {
        if (!volumeControl.contains(e.target)) {
            volumeControl.classList.remove("open");
        }
    });

    // Handle slider input (debounced)
    volumeSlider.addEventListener("input", function () {
        var val = parseInt(volumeSlider.value, 10);
        updateVolumeIcon(val);
        clearTimeout(volumeDebounce);
        volumeDebounce = setTimeout(function () {
            fetch("/api/volume/" + val, { method: "POST" }).catch(function () {});
        }, 150);
    });

    function updateVolumeIcon(vol) {
        var w1 = volumeBtn.querySelector(".vol-wave-1");
        var w2 = volumeBtn.querySelector(".vol-wave-2");
        if (w1) w1.style.display = vol > 5 ? "" : "none";
        if (w2) w2.style.display = vol > 40 ? "" : "none";
        volumeBtn.classList.toggle("muted", vol === 0);
    }

    // Start
    connect();
})();
