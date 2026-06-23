import json
import os
import subprocess
import threading
import tkinter as tk
from tkinter import scrolledtext
from pathlib import Path
from fouria_avatar import FouriaAvatar
from urllib.request import Request, urlopen
from studio_automation import build_in_fl

BASE = "http://127.0.0.1:11700"
BG, PANEL, PURPLE, TEXT, MUTED = "#101016", "#191923", "#a855f7", "#f5f3ff", "#aaa3b8"

def post(path, payload, timeout=240):
    req = Request(BASE + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())

class FouriaChat:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FOURIA • FL Studio Assistant")
        self.root.geometry("430x760+1450+120")
        self.root.minsize(360, 520)
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.messages = []
        header = tk.Frame(self.root, bg=PANEL, height=154)
        header.pack(fill="x")
        self.avatar = FouriaAvatar(header, width=146, height=146)
        self.avatar.pack(side="left", padx=(8, 4), pady=4)
        identity = tk.Frame(header, bg=PANEL)
        identity.pack(side="left", fill="both", expand=True)
        tk.Label(identity, text="FOURIA", fg=PURPLE, bg=PANEL, font=("Segoe UI Semibold", 20)).pack(anchor="w", pady=(12, 0))
        tk.Label(identity, text="your FL Studio copilot • local & private", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w")
        controls = tk.Frame(self.root, bg=BG)
        controls.pack(fill="x", padx=12, pady=10)
        for label, action in [("▶ Play", "play"), ("■ Stop", "stop"), ("● Record", "record"), ("Mixer", "show_mixer"), ("Playlist", "show_playlist")]:
            tk.Button(controls, text=label, command=lambda a=action: self.action(a), bg=PANEL, fg=TEXT,
                      activebackground=PURPLE, activeforeground="white", relief="flat", padx=8, pady=6).pack(side="left", padx=2)
        self.chat = scrolledtext.ScrolledText(self.root, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                                              wrap="word", font=("Segoe UI", 10), padx=14, pady=12, state="disabled")
        self.chat.pack(fill="both", expand=True, padx=8)
        composer = tk.Frame(self.root, bg=PANEL)
        composer.pack(fill="x", padx=10, pady=10)
        self.entry = tk.Text(composer, height=3, bg="#232330", fg=TEXT, insertbackground=TEXT, relief="flat",
                             wrap="word", font=("Segoe UI", 10), padx=10, pady=8)
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.entry.bind("<Control-Return>", lambda _: self.send())
        tk.Button(composer, text="Send", command=self.send, bg=PURPLE, fg="white", activebackground="#9333ea",
                  relief="flat", font=("Segoe UI Semibold", 10), padx=16).pack(side="right", fill="y")
        self.say("FOURIA", "I’m in the studio. Ask me for chords, melodies, drum bounce, arrangement, mixing, or mastering.")
        self.root.after(1500, self.watch_fl)
        autorun = os.environ.get("FOURIA_AUTORUN", "").strip()
        if autorun:
            self.entry.insert("1.0", autorun)
            self.root.after(1200, self.send)

    def say(self, who, text):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{who}\n", ("name",))
        self.chat.insert("end", text.strip() + "\n\n")
        self.chat.tag_config("name", foreground=PURPLE, font=("Segoe UI Semibold", 10))
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def action(self, action):
        threading.Thread(target=lambda: post("/api/fl/action", {"action": action}, 10), daemon=True).start()

    def send(self):
        text = self.entry.get("1.0", "end").strip()
        if not text: return
        self.entry.delete("1.0", "end")
        self.say("YOU", text)
        self.avatar.set_state("thinking")
        self.messages.append({"role": "user", "content": text})
        self.say("FOURIA", "Working in FL Studio…")
        threading.Thread(target=self.execute_or_reply, args=(text,), daemon=True).start()

    def execute_or_reply(self, text):
        lowered = text.lower()
        if "make" in lowered and "chord" in lowered:
            plugin = "Omnisphere" if "omnisphere" in lowered else "FLEX"
            try:
                result = post("/api/chord-midi", {"key": "F", "scale": "minor", "bpm": 130, "bars": 8, "style": "trap"})
                build_in_fl(result["path"], plugin)
                chart = " | ".join("-".join(c["notes"]) for c in result["chords"][:4])
                answer = f"Done. I loaded {plugin} and imported an 8-bar F minor trap progression into its Piano Roll.\n\n{chart}"
                self.messages.append({"role": "assistant", "content": answer})
                self.root.after(0, lambda: self.say("FOURIA", answer))
                return
            except Exception as exc:
                error_message = f"I generated the chords, but FL automation stopped: {exc}"
                self.root.after(0, lambda message=error_message: self.say("FOURIA", message))
                return
        try:
            plan = post("/api/agent/execute", {"request": text}, 20)
            if plan.get("queued"):
                names = ", ".join(item["action"].replace("_", " ") for item in plan["queued"])
                if plan.get("fl_connected"):
                    self.root.after(0, lambda: self.deliver("Executing in FL Studio: " + names + ". I’ll verify through the bridge result and project snapshot."))
                else:
                    self.root.after(0, lambda: self.deliver("I planned the FL actions, but the native bridge is disconnected. Activate FOURIA AI Studio Assistant on a MIDI input before I claim execution."))
                return
        except Exception:
            pass
        self.reply()

    def reply(self):
        try:
            result = post("/api/chat", {"messages": self.messages, "options": {"num_predict": 700}})
            answer = result.get("message", {}).get("content", "I couldn't generate a response.")
            self.messages.append({"role": "assistant", "content": answer})
        except Exception as exc:
            try:
                status = post("/api/agent/plan", {"request": self.messages[-1]["content"]}, 10)
                answer = ("The language model is temporarily unavailable, but the native FL agent is still online. "
                          f"Detected intent: {status.get('intent', 'production_help')}. "
                          "No unverified FL change was reported as complete.")
            except Exception:
                answer = f"I lost the local model connection: {exc}"
        self.root.after(0, lambda: self.deliver(answer))

    def deliver(self, answer):
        self.avatar.set_state("speaking")
        self.say("FOURIA", answer)
        duration = min(9000, max(1400, len(answer) * 28))
        self.root.after(duration, lambda: self.avatar.set_state("idle"))

    def watch_fl(self):
        if os.environ.get("FOURIA_KEEP_OPEN") == "1":
            self.root.after(1500, self.watch_fl)
            return
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq FL64.exe"], capture_output=True, text=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if "FL64.exe" not in result.stdout:
            self.root.destroy()
        else:
            self.root.after(1500, self.watch_fl)

if __name__ == "__main__":
    FouriaChat().root.mainloop()
