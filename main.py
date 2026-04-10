#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import can
from can import Listener
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PGN_DM1 = 0xFECA
PGN_DM2 = 0xFECB
PGN_DM3 = 0xFECD


class J1939Listener(Listener):
    def __init__(self, text_widget, filter_dm1=True):
        self.text_widget = text_widget
        self.filter_dm1 = filter_dm1
        self.running = False
        self.lock = threading.Lock()

    def on_message_received(self, msg):
        if not self.running:
            return

        if self.filter_dm1 and msg.is_j1939:
            pgn = (msg.arbitration_id >> 8) & 0x3FFFF
            if pgn == PGN_DM1:
                return

        with self.lock:
            timestamp = f"{msg.timestamp:.4f}"
            if msg.is_j1939:
                pgn = (msg.arbitration_id >> 8) & 0x3FFFF
                priority = (msg.arbitration_id >> 26) & 0x7
                pdu_format = msg.arbitration_id & 0xFF
                pdu_specific = (msg.arbitration_id >> 8) & 0xFF
                source = (msg.arbitration_id >> 8) & 0xFF
                dest = (msg.arbitration_id >> 16) & 0xFF

                pgn_str = f"PGN:{pgn:05X}"
                data_hex = " ".join(f"{b:02X}" for b in msg.data)
                line = f"[{timestamp}] P:{priority} PF:{pdu_format:02X} PS:{pdu_specific:02X} SA:{source:02X} DA:{dest:02X} {data_hex}\n"
            else:
                data_hex = " ".join(f"{b:02X}" for b in msg.data)
                line = f"[{timestamp}] ID:{msg.arbitration_id:08X} DLC:{msg.dlc} {data_hex}\n"

            self.text_widget.insert(tk.END, line)
            self.text_widget.see(tk.END)

    def start(self):
        with self.lock:
            self.running = True

    def stop(self):
        with self.lock:
            self.running = False


class CANControlPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("J1939 CAN Control Panel")
        self.root.geometry("900x600")

        self.bus = None
        self.listener = None
        self.notifier = None
        self.is_listening = False

        self.create_widgets()

    def create_widgets(self):
        control_frame = ttk.LabelFrame(self.root, text="CAN Connection", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(control_frame, text="Channel:").grid(row=0, column=0, sticky=tk.W)
        self.channel_var = tk.StringVar(value="0")
        ttk.Entry(control_frame, textvariable=self.channel_var, width=10).grid(
            row=0, column=1, padx=5
        )

        ttk.Label(control_frame, text="Baudrate:").grid(row=0, column=2, padx=(10, 0))
        self.baudrate_var = tk.StringVar(value="250000")
        ttk.Entry(control_frame, textvariable=self.baudrate_var, width=10).grid(
            row=0, column=3, padx=5
        )

        self.connect_btn = ttk.Button(
            control_frame, text="Connect", command=self.toggle_connection
        )
        self.connect_btn.grid(row=0, column=4, padx=10)

        self.status_label = ttk.Label(
            control_frame, text="Disconnected", foreground="red"
        )
        self.status_label.grid(row=0, column=5)

        listener_frame = ttk.LabelFrame(self.root, text="CAN Listener", padding=10)
        listener_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.filter_dm1_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            listener_frame, text="Filter out DM1 messages", variable=self.filter_dm1_var
        ).pack(anchor=tk.W)

        btn_frame = ttk.Frame(listener_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        self.listen_btn = ttk.Button(
            btn_frame,
            text="Start Listening",
            command=self.toggle_listening,
            state=tk.DISABLED,
        )
        self.listen_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Clear", command=self.clear_text).pack(
            side=tk.LEFT, padx=5
        )

        self.text_area = scrolledtext.ScrolledText(
            listener_frame, height=20, width=100, font=("Courier", 9)
        )
        self.text_area.pack(fill=tk.BOTH, expand=True)

        dm_frame = ttk.LabelFrame(self.root, text="DM1 Control", padding=10)
        dm_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(dm_frame, text="Target ECU Address (hex):").pack(side=tk.LEFT, padx=5)
        self.target_ecu_var = tk.StringVar(value="00")
        ttk.Entry(dm_frame, textvariable=self.target_ecu_var, width=5).pack(
            side=tk.LEFT
        )

        ttk.Button(dm_frame, text="Clear DM1 (Send DM2)", command=self.clear_dm1).pack(
            side=tk.LEFT, padx=20
        )

        ttk.Button(dm_frame, text="Request DM1", command=self.request_dm1).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Button(dm_frame, text="Clear All DM (DM3)", command=self.clear_all_dm).pack(
            side=tk.LEFT, padx=5
        )

    def toggle_connection(self):
        if self.bus is None:
            self.connect()
        else:
            self.disconnect()

    def connect(self):
        try:
            channel = int(self.channel_var.get())
            baudrate = int(self.baudrate_var.get())

            self.bus = can.interface.Bus(
                bustype="ixxat", channel=channel, bitrate=baudrate
            )

            self.connect_btn.config(text="Disconnect")
            self.status_label.config(text="Connected", foreground="green")
            self.listen_btn.config(state=tk.NORMAL)

            self.log(f"Connected to IXXAT CAN channel {channel} at {baudrate} baud")

        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {e}")
            logger.error(f"Connection error: {e}")

    def disconnect(self):
        if self.is_listening:
            self.toggle_listening()

        if self.bus:
            self.bus.shutdown()
            self.bus = None

        self.connect_btn.config(text="Connect")
        self.status_label.config(text="Disconnected", foreground="red")
        self.listen_btn.config(state=tk.DISABLED)
        self.log("Disconnected from CAN")

    def toggle_listening(self):
        if not self.is_listening:
            self.start_listening()
        else:
            self.stop_listening()

    def start_listening(self):
        if self.bus is None:
            return

        self.listener = J1939Listener(
            self.text_area, filter_dm1=self.filter_dm1_var.get()
        )
        self.notifier = can.Notifier(self.bus, [self.listener])
        self.listener.start()
        self.is_listening = True
        self.listen_btn.config(text="Stop Listening")
        self.log("Started listening to CAN traffic")

    def stop_listening(self):
        if self.listener:
            self.listener.stop()
        if self.notifier:
            self.notifier.stop()
        self.is_listening = False
        self.listen_btn.config(text="Start Listening")
        self.log("Stopped listening to CAN traffic")

    def clear_text(self):
        self.text_area.delete(1.0, tk.END)

    def log(self, message):
        self.text_area.insert(tk.END, f"[LOG] {message}\n")
        self.text_area.see(tk.END)

    def get_target_ecu(self):
        try:
            return int(self.target_ecu_var.get(), 16)
        except ValueError:
            messagebox.showerror(
                "Invalid Input", "Please enter a valid hex address (e.g., 00, FF)"
            )
            return None

    def send_j1939_request(self, pgn, dest=0xFF):
        if self.bus is None:
            messagebox.showwarning("Not Connected", "Please connect to CAN first")
            return False

        request_data = [
            pgn & 0xFF,
            (pgn >> 8) & 0xFF,
            (pgn >> 16) & 0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
        ]

        arb_id = (7 << 26) | (0xEA << 8) | (dest << 8) | 0xFF

        msg = can.Message(
            arbitration_id=arb_id, data=request_data, is_extended_id=True, is_j1939=True
        )

        try:
            self.bus.send(msg)
            self.log(f"Sent PGN {pgn:06X} request to destination {dest:02X}")
            return True
        except Exception as e:
            messagebox.showerror("Send Error", f"Failed to send message: {e}")
            return False

    def send_j1939_command(self, pgn, data, dest=None):
        if self.bus is None:
            messagebox.showwarning("Not Connected", "Please connect to CAN first")
            return False

        if dest is None:
            dest = self.get_target_ecu()
            if dest is None:
                return False

        while len(data) < 8:
            data.append(0xFF)

        arb_id = (7 << 26) | (pgn << 8) | dest

        msg = can.Message(
            arbitration_id=arb_id, data=data[:8], is_extended_id=True, is_j1939=True
        )

        try:
            self.bus.send(msg)
            self.log(f"Sent PGN {pgn:06X} command to ECU {dest:02X}")
            return True
        except Exception as e:
            messagebox.showerror("Send Error", f"Failed to send message: {e}")
            return False

    def clear_dm1(self):
        dest = self.get_target_ecu()
        if dest is None:
            return

        self.send_j1939_command(PGN_DM2, [0x01], dest=dest)

    def request_dm1(self):
        dest = self.get_target_ecu()
        if dest is None:
            return

        self.send_j1939_request(PGN_DM1, dest=dest)

    def clear_all_dm(self):
        dest = self.get_target_ecu()
        if dest is None:
            return

        self.send_j1939_command(PGN_DM3, [0x01], dest=dest)

    def on_close(self):
        if self.is_listening:
            self.stop_listening()
        if self.bus:
            self.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = CANControlPanel(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
