#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime
from typing import Dict

from can_service import CANService, DecodedMessage


class CANControlPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("J1939 CAN Control Panel")
        self.root.geometry("1000x700")

        self.can_service = CANService()
        self.can_service.set_message_callback(self._on_can_message)
        self.can_service.set_status_callback(self._on_status_message)

        self.show_updates_only = tk.BooleanVar(value=True)
        self.filter_dm1_var = tk.BooleanVar(value=True)
        self.show_raw_var = tk.BooleanVar(value=True)

        self._message_rows: Dict[int, str] = {}

        self.create_widgets()

    def create_widgets(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=2)

        ttk.Button(toolbar, text="Load DBC File", command=self.load_dbc).pack(
            side=tk.LEFT, padx=2
        )
        self.dbc_label = ttk.Label(toolbar, text="No DBC loaded", foreground="gray")
        self.dbc_label.pack(side=tk.LEFT, padx=10)

        control_frame = ttk.LabelFrame(self.root, text="CAN Connection", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(control_frame, text="Channel:").grid(row=0, column=0, sticky=tk.W)
        self.channel_var = tk.StringVar(value="0")
        ttk.Entry(control_frame, textvariable=self.channel_var, width=8).grid(
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
        self.status_label.grid(row=0, column=5, padx=10)

        self.listen_btn = ttk.Button(
            control_frame,
            text="Start Listening",
            command=self.toggle_listening,
            state=tk.DISABLED,
        )
        self.listen_btn.grid(row=0, column=6, padx=10)

        options_frame = ttk.LabelFrame(self.root, text="Display Options", padding=5)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Checkbutton(
            options_frame, text="Show updates only", variable=self.show_updates_only
        ).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(
            options_frame, text="Filter DM1", variable=self.filter_dm1_var
        ).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(
            options_frame, text="Show raw data", variable=self.show_raw_var
        ).pack(side=tk.LEFT, padx=10)

        messages_frame = ttk.LabelFrame(self.root, text="CAN Messages", padding=5)
        messages_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree_frame = ttk.Frame(messages_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("timestamp", "can_id", "name", "update", "decoded")
        self.message_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=15
        )

        self.message_tree.heading("timestamp", text="Time")
        self.message_tree.heading("can_id", text="CAN ID")
        self.message_tree.heading("name", text="Message")
        self.message_tree.heading("update", text="Update")
        self.message_tree.heading("decoded", text="Decoded Values")

        self.message_tree.column("timestamp", width=80)
        self.message_tree.column("can_id", width=100)
        self.message_tree.column("name", width=150)
        self.message_tree.column("update", width=60)
        self.message_tree.column("decoded", width=500)

        scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self.message_tree.yview
        )
        self.message_tree.configure(yscrollcommand=scrollbar.set)

        self.message_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(messages_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text="Clear Messages", command=self.clear_messages).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            btn_frame, text="Refresh Display", command=self.refresh_display
        ).pack(side=tk.LEFT, padx=5)

        log_frame = ttk.LabelFrame(self.root, text="Log", padding=5)
        log_frame.pack(fill=tk.X, padx=10, pady=5, ipady=50)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=6, font=("Courier", 8)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        dm_frame = ttk.LabelFrame(self.root, text="DM1 Control", padding=10)
        dm_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(dm_frame, text="Target ECU (hex):").pack(side=tk.LEFT, padx=5)
        self.target_ecu_var = tk.StringVar(value="00")
        ttk.Entry(dm_frame, textvariable=self.target_ecu_var, width=5).pack(
            side=tk.LEFT
        )

        ttk.Button(dm_frame, text="Clear DM1", command=self.clear_dm1).pack(
            side=tk.LEFT, padx=10
        )
        ttk.Button(dm_frame, text="Request DM1", command=self.request_dm1).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(dm_frame, text="Clear All DM", command=self.clear_all_dm).pack(
            side=tk.LEFT, padx=5
        )

    def load_dbc(self):
        filepath = filedialog.askopenfilename(
            title="Select DBC File",
            filetypes=[("DBC files", "*.dbc"), ("All files", "*.*")],
        )
        if filepath:
            if self.can_service.load_dbc(filepath):
                self.dbc_label.config(text=filepath.split("/")[-1], foreground="green")
            else:
                messagebox.showerror(
                    "DBC Error",
                    "Failed to load DBC file. Install cantools: pip install cantools",
                )

    def toggle_connection(self):
        if self.can_service.is_connected():
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        try:
            channel = int(self.channel_var.get())
            baudrate = int(self.baudrate_var.get())

            if self.can_service.connect(channel, baudrate):
                self.connect_btn.config(text="Disconnect")
                self.status_label.config(text="Connected", foreground="green")
                self.listen_btn.config(state=tk.NORMAL)
        except ValueError:
            messagebox.showerror(
                "Invalid Input", "Please enter valid numbers for channel and baudrate"
            )

    def disconnect(self):
        if self.can_service.is_listening:
            self.toggle_listening()
        self.can_service.disconnect()
        self.connect_btn.config(text="Connect")
        self.status_label.config(text="Disconnected", foreground="red")
        self.listen_btn.config(state=tk.DISABLED)

    def toggle_listening(self):
        if not self.can_service.is_listening:
            self.start_listening()
        else:
            self.stop_listening()

    def start_listening(self):
        self.can_service.start_listening(filter_dm1=self.filter_dm1_var.get())
        self.listen_btn.config(text="Stop Listening")

    def stop_listening(self):
        self.can_service.stop_listening()
        self.listen_btn.config(text="Start Listening")

    def clear_messages(self):
        for item in self.message_tree.get_children():
            self.message_tree.delete(item)
        self._message_rows.clear()

    def refresh_display(self):
        pass

    def _on_can_message(self, msg: DecodedMessage):
        def update_gui():
            if self.show_updates_only.get() and not msg.is_update:
                return

            timestamp = datetime.fromtimestamp(msg.timestamp).strftime("%H:%M:%S.%f")[
                :-3
            ]
            can_id_str = f"{msg.can_id:08X}"

            if msg.dbc_name:
                name = msg.dbc_name
                decoded_str = ", ".join(
                    f"{k}={v}" for k, v in msg.decoded_fields.items()
                )
            else:
                name = ""
                decoded_str = ""

            update_char = "*" if msg.is_update else " "

            if msg.can_id in self._message_rows:
                item = self._message_rows[msg.can_id]
                self.message_tree.item(
                    item, values=(timestamp, can_id_str, name, update_char, decoded_str)
                )
            else:
                item = self.message_tree.insert(
                    "",
                    0,
                    values=(timestamp, can_id_str, name, update_char, decoded_str),
                )
                self._message_rows[msg.can_id] = item

        self.root.after(0, update_gui)

    def _on_status_message(self, message: str):
        def update_log():
            self.log_text.insert(
                tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {message}\n"
            )
            self.log_text.see(tk.END)

        self.root.after(0, update_log)

    def get_target_ecu(self) -> int:
        try:
            return int(self.target_ecu_var.get(), 16)
        except ValueError:
            messagebox.showerror(
                "Invalid Input", "Please enter a valid hex address (e.g., 00, FF)"
            )
            return -1

    def clear_dm1(self):
        dest = self.get_target_ecu()
        if dest >= 0:
            self.can_service.clear_dm1(dest)

    def request_dm1(self):
        dest = self.get_target_ecu()
        if dest >= 0:
            self.can_service.request_dm1(dest)

    def clear_all_dm(self):
        dest = self.get_target_ecu()
        if dest >= 0:
            self.can_service.clear_all_dm(dest)

    def on_close(self):
        self.can_service.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = CANControlPanel(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
