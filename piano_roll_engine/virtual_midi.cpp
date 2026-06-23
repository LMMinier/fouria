// virtual_midi.cpp
// FOURIA Piano Roll Engine -- C++ virtual MIDI sender for Windows
// Compile: cl.exe virtual_midi.cpp /link winmm.lib
// Usage:   virtual_midi.exe notes.json [bpm]
//
// notes.json format:
// {"bpm": 140, "ticks_per_beat": 480, "events": [
//   {"note": 60, "start_ticks": 0, "duration_ticks": 480, "velocity": 88},
//   ...
// ]}

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#pragma comment(lib, "winmm.lib")

// -- Minimal JSON parser for our specific format ----------------------------

typedef struct {
    int note;
    int start_ticks;
    int duration_ticks;
    int velocity;
} NoteEvent;

// Very small JSON int extractor -- no external deps
static int json_int(const char* json, const char* key, int default_val) {
    char search[64];
    snprintf(search, sizeof(search), "\"%s\"", key);
    const char* pos = strstr(json, search);
    if (!pos) return default_val;
    pos = strchr(pos, ':');
    if (!pos) return default_val;
    while (*pos == ':' || *pos == ' ') pos++;
    return atoi(pos);
}

// -- MIDI port finder -------------------------------------------------------

static UINT find_loopmidi_port(void) {
    UINT num = midiOutGetNumDevs();
    MIDIOUTCAPS caps;
    for (UINT i = 0; i < num; i++) {
        midiOutGetDevCaps(i, &caps, sizeof(caps));
        // Look for loopMIDI, FOURIA, or virtual in name
        char name[32];
        for (int j = 0; j < 32; j++) name[j] = (char)caps.szPname[j];
        _strlwr_s(name, sizeof(name));
        if (strstr(name, "loopmidi") || strstr(name, "fouria") ||
            strstr(name, "virtual") || strstr(name, "loop")) {
            return i;
        }
    }
    return 0; // fallback to first port
}

// -- Timeline event ---------------------------------------------------------

typedef struct {
    double time_sec;
    DWORD  msg;
} TimedMsg;

static int cmp_timed(const void* a, const void* b) {
    double diff = ((TimedMsg*)a)->time_sec - ((TimedMsg*)b)->time_sec;
    return diff < 0 ? -1 : diff > 0 ? 1 : 0;
}

// -- Main -------------------------------------------------------------------

int main(int argc, char* argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: virtual_midi.exe notes.json\n");
        return 1;
    }

    // Read JSON file
    FILE* f = fopen(argv[1], "r");
    if (!f) { fprintf(stderr, "Cannot open %s\n", argv[1]); return 1; }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    rewind(f);
    char* json = (char*)malloc(size + 1);
    fread(json, 1, size, f);
    json[size] = 0;
    fclose(f);

    int bpm            = json_int(json, "bpm", 140);
    int ticks_per_beat = json_int(json, "ticks_per_beat", 480);

    // Parse events array
    // Simple: scan for all {"note": occurrences
    NoteEvent events[4096];
    int n_events = 0;
    const char* p = json;
    while ((p = strstr(p, "\"note\"")) && n_events < 4096) {
        NoteEvent ev;
        // Back up to find the { for this object
        ev.note           = json_int(p, "note", 60);
        ev.start_ticks    = json_int(p, "start_ticks", 0);
        // Also support "start" key (our MIDI spec uses "start")
        if (ev.start_ticks == 0) ev.start_ticks = json_int(p, "start", 0);
        ev.duration_ticks = json_int(p, "duration_ticks", 480);
        if (ev.duration_ticks == 480) ev.duration_ticks = json_int(p, "duration", 480);
        ev.velocity       = json_int(p, "velocity", 88);
        events[n_events++] = ev;
        p += 6; // move past "note"
    }
    free(json);

    if (n_events == 0) {
        fprintf(stderr, "No events found in JSON.\n");
        return 1;
    }

    // Build timed message list
    double beat_sec = 60.0 / bpm;
    double tick_sec = beat_sec / ticks_per_beat;
    TimedMsg msgs[8192];
    int n_msgs = 0;
    for (int i = 0; i < n_events && n_msgs + 2 <= 8192; i++) {
        int note = events[i].note & 0x7F;
        int vel  = events[i].velocity & 0x7F;
        double t_on  = events[i].start_ticks * tick_sec;
        double t_off = (events[i].start_ticks + events[i].duration_ticks) * tick_sec;
        msgs[n_msgs].time_sec = t_on;
        msgs[n_msgs].msg      = (DWORD)(0x00900000 | (note << 8) | vel);
        n_msgs++;
        msgs[n_msgs].time_sec = t_off;
        msgs[n_msgs].msg      = (DWORD)(0x00800000 | (note << 8));
        n_msgs++;
    }
    qsort(msgs, n_msgs, sizeof(TimedMsg), cmp_timed);

    // Open MIDI port
    HMIDIOUT hMidi;
    UINT port = find_loopmidi_port();
    MMRESULT res = midiOutOpen(&hMidi, port, 0, 0, CALLBACK_NULL);
    if (res != MMSYSERR_NOERROR) {
        fprintf(stderr, "Failed to open MIDI port %u (error %u)\n", port, res);
        return 1;
    }

    MIDIOUTCAPS caps;
    midiOutGetDevCaps(port, &caps, sizeof(caps));
    printf("FOURIA Piano Roll Engine: sending %d notes to '%ls' at %d BPM\n",
           n_events, caps.szPname, bpm);

    // Send with high-resolution timing
    LARGE_INTEGER freq, start, now;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&start);

    for (int i = 0; i < n_msgs; i++) {
        double target = msgs[i].time_sec;
        // Spin-wait for accuracy (sleep most, spin the last 2ms)
        double elapsed;
        do {
            QueryPerformanceCounter(&now);
            elapsed = (double)(now.QuadPart - start.QuadPart) / freq.QuadPart;
            if (target - elapsed > 0.002) Sleep(1);
        } while (elapsed < target);
        midiOutShortMsg(hMidi, msgs[i].msg);
    }

    // All notes off
    for (int ch = 0; ch < 16; ch++)
        midiOutShortMsg(hMidi, (DWORD)(0xB0 | ch | (123 << 8)));

    midiOutClose(hMidi);
    printf("Done. %d notes sent.\n", n_events);
    return 0;
}
