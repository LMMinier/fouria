CAPABILITIES = {
    "chat_production_coach": {"status": "verified", "evidence": "local model + RAG"},
    "chord_generation": {"status": "verified", "evidence": "MIDI generated and imported into Omnisphere Piano Roll"},
    "melody_midi": {"status": "implemented", "evidence": "generator tested; FL placement needs per-command verification"},
    "drums_808_midi": {"status": "implemented", "evidence": "generator tested; lane splitting remains manual"},
    "fl_transport": {"status": "implemented", "evidence": "native bridge v2 action/result protocol; requires active MIDI script"},
    "project_snapshot": {"status": "implemented", "evidence": "channels, plugins, routing, mixer levels, peaks, slots, pattern and project state"},
    "native_channel_control": {"status": "implemented", "evidence": "name, volume, pan, pitch, mute, solo, selection, routing, quantize and step grid"},
    "native_mixer_control": {"status": "implemented", "evidence": "name, volume, pan, width, mute, solo, routing, sends, plugin mix and parameters"},
    "project_organization": {"status": "implemented", "evidence": "unique channel-to-mixer routing and mirrored naming with undo point"},
    "initial_gain_staging": {"status": "implemented", "evidence": "role-aware static balance with undo point and bridge result"},
    "wav_level_analysis": {"status": "implemented", "evidence": "offline peak/RMS/crest/clipping/DC analysis"},
    "mix_planning": {"status": "implemented", "evidence": "structured plan; automatic plugin decisions not yet verified"},
    "master_planning": {"status": "implemented", "evidence": "structured plan; automatic rendering not yet verified"},
    "automatic_full_mix": {"status": "not_verified", "evidence": "requires stem analysis and safe per-channel FL control"},
    "automatic_full_master": {"status": "not_verified", "evidence": "requires spectral/loudness/true-peak analysis and render verification"},
    "full_song_creation": {"status": "partial", "evidence": "musical generators exist; complete arrangement and sound-selection executor pending"},
}


def report():
    return {"ok": True, "capabilities": CAPABILITIES}
