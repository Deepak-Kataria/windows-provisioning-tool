"""Network: adapter info, static IP / DHCP, enable / disable adapter, mapped network drives."""
import re
import threading
import tkinter.messagebox as msgbox

import customtkinter as ctk

from modules.logger import log
from modules.runner import run_inline_powershell
from ui import theme as T
from ui.widgets import LogDrawer, confirm_run, section_header, tip


def _parse_kv(out: str) -> dict:
    data = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    return data


class NetworkTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._net_adapters = []
        self._current_net_adapter = ""
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1, uniform="col")
        self.grid_columnconfigure(1, weight=1, uniform="col")
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.grid_columnconfigure(0, weight=1)
        right = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)

        # ── Adapter ─────────────────────────────────────────────────
        hdr, col = section_header(left, "Network adapter", height=30)
        hdr.grid(row=0, column=0, sticky="ew")
        self._net_toggle_btn = ctk.CTkButton(hdr, text="Disable", width=80, height=22, font=T.ui(11),
                                             fg_color=T.DANGER, hover_color=T.DANGER_HOVER,
                                             command=self._toggle_adapter)
        self._net_toggle_btn.grid(row=0, column=col + 1, padx=(8, 4))
        tip(self._net_toggle_btn, "Disable or enable the selected adapter (asks first)")
        self._refresh_net_btn = T.outline_button(hdr, text="Refresh", width=76, height=22, font=T.ui(11),
                                                 command=self._fetch_network_info)
        self._refresh_net_btn.grid(row=0, column=col + 2, padx=(0, 8))
        tip(self._refresh_net_btn, "Read adapter settings again")

        card = ctk.CTkFrame(left, fg_color=T.PANEL, corner_radius=0)
        card.grid(row=1, column=0, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        self._net_adapter_var = ctk.StringVar()
        self._net_adapter_menu = ctk.CTkOptionMenu(
            card, variable=self._net_adapter_var, values=["—"],
            command=self._on_adapter_select, height=28)
        self._net_adapter_menu.grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 4), sticky="ew")
        self._net_adapter_menu.grid_remove()

        self._net_adapter_entry = self._field(card, 1, "ADAPTER")
        self._net_ip_entry = self._field(card, 2, "IP ADDRESS", mono=True)
        self._net_subnet_entry = self._field(card, 3, "PREFIX", mono=True)
        self._net_gw_entry = self._field(card, 4, "GATEWAY", mono=True)
        self._net_dns_entry = self._field(card, 5, "DNS SERVERS", mono=True)
        self._net_mac_entry = self._field(card, 6, "MAC", mono=True)

        ctk.CTkLabel(card, text="Edit IP / prefix / gateway / DNS, then apply as static, or reset to DHCP.",
                     font=T.ui(11), text_color=T.MUTED, anchor="w").grid(
            row=7, column=0, columnspan=2, padx=12, pady=(6, 2), sticky="w")
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=8, column=0, columnspan=2, padx=12, pady=(4, 12), sticky="e")
        self._set_dhcp_btn = T.outline_button(btns, text="Set to DHCP", width=110, height=28,
                                              command=self._set_dhcp)
        self._set_dhcp_btn.grid(row=0, column=0, padx=(0, 8))
        tip(self._set_dhcp_btn, "Get IP and DNS automatically (asks first)")
        self._apply_ip_btn = ctk.CTkButton(btns, text="Apply Static IP", width=130, height=28,
                                           command=self._apply_static_ip)
        self._apply_ip_btn.grid(row=0, column=1)
        tip(self._apply_ip_btn, "Set the values above as a static IP (asks first)")

        # ── Drive mapper ────────────────────────────────────────────
        hdr, col = section_header(right, "Mapped drives", height=30)
        hdr.grid(row=0, column=0, sticky="ew")
        self._dm_disconnect_btn = ctk.CTkButton(hdr, text="Disconnect", width=90, height=22, font=T.ui(11),
                                                fg_color=T.DANGER, hover_color=T.DANGER_HOVER,
                                                command=self._dm_disconnect)
        self._dm_disconnect_btn.grid(row=0, column=col + 1, padx=(8, 4))
        tip(self._dm_disconnect_btn, "Disconnect the ticked drives")
        self._dm_refresh_btn = T.outline_button(hdr, text="Refresh", width=76, height=22, font=T.ui(11),
                                                command=self._dm_refresh)
        self._dm_refresh_btn.grid(row=0, column=col + 2, padx=(0, 8))

        self._dm_scroll = ctk.CTkScrollableFrame(right, height=120, fg_color=T.PANEL, corner_radius=0)
        self._dm_scroll.grid(row=1, column=0, sticky="ew")
        self._dm_scroll.grid_columnconfigure(2, weight=1)
        self._dm_checkboxes = {}

        self._dm_status_lbl = ctk.CTkLabel(right, text="", font=T.ui(11), text_color=T.MUTED, anchor="w")
        self._dm_status_lbl.grid(row=2, column=0, padx=4, pady=(4, 0), sticky="w")

        hdr, _ = section_header(right, "Map new drive", height=30)
        hdr.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        form = ctk.CTkFrame(right, fg_color=T.PANEL, corner_radius=0)
        form.grid(row=4, column=0, sticky="ew")
        form.grid_columnconfigure(1, weight=1)
        self._label(form, 0, "LETTER")
        self._dm_letter_var = ctk.StringVar(value="Z:")
        ctk.CTkOptionMenu(form, variable=self._dm_letter_var, height=28, width=80,
                          values=[f"{c}:" for c in "ZYXWVUTSRQPONMLKJIHGFEDCBA"]).grid(
            row=0, column=1, padx=(0, 12), pady=(12, 4), sticky="w")
        self._dm_unc_entry = self._field(form, 1, "UNC PATH", r"\\server\share", mono=True)
        self._dm_user_entry = self._field(form, 2, "USERNAME", r"optional (domain\user)")
        self._dm_pass_entry = self._field(form, 3, "PASSWORD", "optional", secret=True)
        ctk.CTkButton(form, text="Map Drive", width=110, height=28, command=self._dm_map).grid(
            row=4, column=1, padx=12, pady=(6, 12), sticky="e")

        # Output
        self._log = LogDrawer(self, height=140)
        self._log.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._log.append("Ready.")

        self.after(300, self._fetch_network_info)
        self.after(500, self._dm_refresh)

    @staticmethod
    def _label(card, row, text):
        ctk.CTkLabel(card, text=text, font=T.mono(10), text_color=T.MUTED, width=100, anchor="w").grid(
            row=row, column=0, padx=(12, 6), pady=(12 if row == 0 else 4, 4), sticky="w")

    def _field(self, card, row, label, placeholder="", secret=False, mono=False):
        self._label(card, row, label)
        e = ctk.CTkEntry(card, height=28, placeholder_text=placeholder, show="*" if secret else "",
                         font=T.mono(11) if mono else T.ui(12))
        e.grid(row=row, column=1, padx=(0, 12), pady=(12 if row == 0 else 4, 4), sticky="ew")
        return e

    # ── Network fetch ─────────────────────────────────────────────────

    def _fetch_network_info(self):
        self._refresh_net_btn.configure(text="Refreshing...", state="disabled")
        cmd = (
            "$adapters = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -or $_.Status -eq 'Disabled' } | Sort-Object ifIndex; "
            "$idx = 0; "
            "foreach ($a in $adapters) { "
            "  $ip='N/A'; $prefix='N/A'; $gw='N/A'; $dns='N/A'; $skip=$false; "
            "  if ($a.Status -eq 'Up') { "
            "    $cfg = Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1; "
            "    if ($cfg) { "
            "      $ip=$cfg.IPAddress; $prefix=\"/$($cfg.PrefixLength)\"; "
            "      $gwN=(Get-NetRoute -InterfaceIndex $a.ifIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object -First 1).NextHop; "
            "      $gw=if($gwN){$gwN}else{'N/A'}; "
            "      $dA=(Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses; "
            "      $dns=if($dA){$dA -join ', '}else{'N/A'} "
            "    } else { $skip=$true } "
            "  }; "
            "  if (-not $skip) { "
            "    Write-Host \"NAME_${idx}: $($a.Name)\"; "
            "    Write-Host \"DESC_${idx}: $($a.InterfaceDescription)\"; "
            "    Write-Host \"STATUS_${idx}: $($a.Status)\"; "
            "    Write-Host \"IP_${idx}: $ip\"; "
            "    Write-Host \"PREFIX_${idx}: $prefix\"; "
            "    Write-Host \"GW_${idx}: $gw\"; "
            "    Write-Host \"DNS_${idx}: $dns\"; "
            "    Write-Host \"MAC_${idx}: $($a.MacAddress)\"; "
            "    $idx++ "
            "  } "
            "}; "
            "Write-Host \"COUNT: $idx\""
        )

        def task():
            rc, out = run_inline_powershell(cmd)

            def done():
                self._refresh_net_btn.configure(text="Refresh", state="normal")
                raw = _parse_kv(out)
                count = int(raw.get("COUNT", "0") or "0")
                self._net_adapters = []
                for i in range(count):
                    self._net_adapters.append({
                        "name":   raw.get(f"NAME_{i}", ""),
                        "desc":   raw.get(f"DESC_{i}", ""),
                        "status": raw.get(f"STATUS_{i}", "Up"),
                        "ip":     raw.get(f"IP_{i}", ""),
                        "prefix": raw.get(f"PREFIX_{i}", ""),
                        "gw":     raw.get(f"GW_{i}", ""),
                        "dns":    raw.get(f"DNS_{i}", ""),
                        "mac":    raw.get(f"MAC_{i}", ""),
                    })
                if not self._net_adapters:
                    self._clear_net_fields()
                    return
                if count > 1:
                    labels = [f"{a['name']}  —  {a['ip']}" for a in self._net_adapters]
                    self._net_adapter_menu.configure(values=labels)
                    self._net_adapter_var.set(labels[0])
                    self._net_adapter_menu.grid()
                else:
                    self._net_adapter_menu.grid_remove()
                self._populate_net_fields(self._net_adapters[0])

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _on_adapter_select(self, label: str):
        for a in self._net_adapters:
            if label.startswith(a["name"]):
                self._populate_net_fields(a)
                break

    def _populate_net_fields(self, a: dict):
        self._current_net_adapter = a["name"]
        is_up = a.get("status", "Up") == "Up"
        self._net_toggle_btn.configure(
            text="Disable" if is_up else "Enable",
            fg_color=T.DANGER if is_up else T.ACCENT,
            hover_color=T.DANGER_HOVER if is_up else T.ACCENT_HOVER,
        )
        for btn in (self._apply_ip_btn, self._set_dhcp_btn):
            btn.configure(state="normal" if is_up else "disabled")

        def _set(entry, val):
            entry.delete(0, "end")
            if val:
                entry.insert(0, val)

        _set(self._net_adapter_entry, f"{a['name']}  ({a['desc']})")
        _set(self._net_ip_entry,      a["ip"])
        _set(self._net_subnet_entry,  a["prefix"])
        _set(self._net_gw_entry,      a["gw"])
        _set(self._net_dns_entry,     a["dns"])
        _set(self._net_mac_entry,     a["mac"])

    def _clear_net_fields(self):
        for e in (self._net_adapter_entry, self._net_ip_entry, self._net_subnet_entry,
                  self._net_gw_entry, self._net_dns_entry, self._net_mac_entry):
            e.delete(0, "end")
            e.insert(0, "No active adapters found")

    # ── Actions ───────────────────────────────────────────────────────

    def _toggle_adapter(self):
        name = self._current_net_adapter
        if not name:
            return
        adapter = next((a for a in self._net_adapters if a["name"] == name), None)
        if not adapter:
            return
        is_up = adapter.get("status", "Up") == "Up"
        action = "Disable" if is_up else "Enable"
        ps_cmd = f"{'Disable' if is_up else 'Enable'}-NetAdapter -Name '{name}' -Confirm:$false; Write-Host 'DONE'"
        if is_up and not confirm_run(self, "Disable adapter?", "This adapter will be disabled:",
                                     [(f"{name}  ({adapter.get('desc', '')})", True)],
                                     action_text="Disable", danger=True,
                                     footer="If this is how you reach the network, you lose the connection."):
            return
        self._net_toggle_btn.configure(state="disabled", text=f"{action}ing...")

        def task():
            rc, out = run_inline_powershell(ps_cmd)

            def done():
                self._net_toggle_btn.configure(state="normal")
                if rc == 0:
                    log(f"Adapter '{name}' {action.lower()}d", "success")
                    self._append_output(f"Adapter '{name}' {action.lower()}d.")
                    self._fetch_network_info()
                else:
                    self._append_output(f"ERROR: Could not {action.lower()} adapter — {out.strip()}")
                    msgbox.showerror("Adapter Toggle Failed", out.strip() or "Unknown error.")

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _apply_static_ip(self):
        name = self._current_net_adapter
        if not name:
            return
        ip          = self._net_ip_entry.get().strip()
        raw_prefix  = self._net_subnet_entry.get().strip().lstrip("/")
        gw          = self._net_gw_entry.get().strip()
        dns         = self._net_dns_entry.get().strip()

        ip_re = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')

        def valid_ip(s):
            return bool(ip_re.match(s)) and all(0 <= int(o) <= 255 for o in s.split("."))

        if not valid_ip(ip):
            msgbox.showerror("Invalid Input", f"Invalid IP address: {ip}")
            return
        if not raw_prefix.isdigit() or not (1 <= int(raw_prefix) <= 32):
            msgbox.showerror("Invalid Input", f"Invalid prefix length: {raw_prefix}  (must be 1–32)")
            return
        prefix = int(raw_prefix)
        gw_val = gw if (gw and gw not in ("N/A", "")) else ""
        if gw_val and not valid_ip(gw_val):
            msgbox.showerror("Invalid Input", f"Invalid gateway: {gw_val}")
            return

        dns_servers = [d.strip() for d in dns.replace(";", ",").split(",")
                       if d.strip() and d.strip() != "N/A"]
        for d in dns_servers:
            if not valid_ip(d):
                msgbox.showerror("Invalid Input", f"Invalid DNS server: {d}")
                return

        gw_arg  = f"-DefaultGateway '{gw_val}'" if gw_val else ""
        dns_cmd = (
            f"Set-DnsClientServerAddress -InterfaceAlias '{name}' "
            f"-ServerAddresses {','.join(repr(d) for d in dns_servers)};"
            if dns_servers else ""
        )
        ps_cmd = (
            f"Set-NetIPInterface -InterfaceAlias '{name}' -Dhcp Disabled -ErrorAction SilentlyContinue; "
            f"Remove-NetIPAddress -InterfaceAlias '{name}' -Confirm:$false -ErrorAction SilentlyContinue; "
            f"Remove-NetRoute -InterfaceAlias '{name}' -DestinationPrefix '0.0.0.0/0' -Confirm:$false -ErrorAction SilentlyContinue; "
            f"New-NetIPAddress -InterfaceAlias '{name}' -IPAddress '{ip}' -PrefixLength {prefix} {gw_arg} | Out-Null; "
            f"{dns_cmd} "
            f"Write-Host 'SUCCESS'"
        )
        if not confirm_run(self, "Apply static IP?", f"Adapter '{name}' will use these settings:",
                           [f"IP       {ip}/{prefix}", f"Gateway  {gw_val or '(none)'}",
                            f"DNS      {', '.join(dns_servers) or '(unchanged)'}"],
                           action_text="Apply", danger=True,
                           footer="The connection drops briefly; wrong values can cut this PC off the network."):
            return
        self._apply_ip_btn.configure(state="disabled", text="Applying...")

        def task():
            rc, out = run_inline_powershell(ps_cmd)

            def done():
                self._apply_ip_btn.configure(state="normal", text="Apply Static IP")
                if rc == 0 and "SUCCESS" in out:
                    log(f"Static IP {ip}/{prefix} applied to '{name}'", "success")
                    self._append_output(f"Static IP {ip}/{prefix} applied to '{name}'.")
                    self._fetch_network_info()
                else:
                    err = out.strip() or "Unknown error."
                    self._append_output(f"ERROR applying IP: {err}")
                    msgbox.showerror("Apply IP Failed", err)

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _set_dhcp(self):
        name = self._current_net_adapter
        if not name:
            return
        ps_cmd = (
            f"Set-NetIPInterface -InterfaceAlias '{name}' -Dhcp Enabled; "
            f"Set-DnsClientServerAddress -InterfaceAlias '{name}' -ResetServerAddresses; "
            f"ipconfig /renew '{name}' | Out-Null; "
            f"Write-Host 'SUCCESS'"
        )
        if not confirm_run(self, "Switch to DHCP?", f"Adapter '{name}' will get its IP and DNS automatically.",
                           [name], action_text="Set to DHCP", footer="The connection drops briefly."):
            return
        self._set_dhcp_btn.configure(state="disabled", text="Setting DHCP...")

        def task():
            rc, out = run_inline_powershell(ps_cmd)

            def done():
                self._set_dhcp_btn.configure(state="normal", text="Set to DHCP")
                if rc == 0 and "SUCCESS" in out:
                    log(f"'{name}' set to DHCP", "success")
                    self._append_output(f"'{name}' set to DHCP.")
                    self._fetch_network_info()
                else:
                    err = out.strip() or "Unknown error."
                    self._append_output(f"ERROR setting DHCP: {err}")
                    msgbox.showerror("Set DHCP Failed", err)

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    # ── Drive Mapper ─────────────────────────────────────────────────

    def _dm_refresh(self):
        self._dm_refresh_btn.configure(state="disabled", text="Refreshing...")
        cmd = (
            "Get-WmiObject -Class Win32_MappedLogicalDisk -ErrorAction SilentlyContinue | "
            "ForEach-Object { Write-Host \"DRIVE: $($_.DeviceID) | $($_.ProviderName)\" }"
        )

        def task():
            rc, out = run_inline_powershell(cmd)

            def done():
                for w in self._dm_scroll.winfo_children():
                    w.destroy()
                self._dm_checkboxes.clear()
                lines = [l for l in out.splitlines() if l.startswith("DRIVE:")]
                small = T.ui(11)
                if not lines:
                    ctk.CTkLabel(self._dm_scroll, text="No network drives mapped.",
                                 text_color=T.MUTED, font=small).grid(row=0, column=0, padx=6, pady=4)
                else:
                    for i, line in enumerate(lines):
                        _, _, rest = line.partition(": ")
                        letter, _, unc = rest.partition(" | ")
                        letter = letter.strip(); unc = unc.strip()
                        var = ctk.BooleanVar(value=False)
                        self._dm_checkboxes[letter] = (var, unc)
                        ctk.CTkCheckBox(self._dm_scroll, text="", variable=var, width=28,
                                        checkbox_width=18, checkbox_height=18).grid(
                            row=i, column=0, padx=(4, 0), pady=2)
                        ctk.CTkLabel(self._dm_scroll, text=letter, width=32, anchor="w",
                                     font=small).grid(row=i, column=1, padx=4, pady=2, sticky="w")
                        ctk.CTkLabel(self._dm_scroll, text=unc, anchor="w",
                                     text_color=T.INFO, font=small).grid(
                            row=i, column=2, padx=4, pady=2, sticky="w")
                self._dm_refresh_btn.configure(state="normal", text="Refresh")

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _dm_map(self):
        letter = self._dm_letter_var.get().rstrip(":")
        unc = self._dm_unc_entry.get().strip()
        user = self._dm_user_entry.get().strip()
        passwd = self._dm_pass_entry.get()
        if not unc:
            self._dm_status_lbl.configure(text="UNC path required.", text_color=T.FAIL)
            return
        if not unc.startswith("\\\\"):
            self._dm_status_lbl.configure(text=r"UNC path must start with \\server\share", text_color=T.FAIL)
            return

        unc_e  = unc.replace("'", "''")
        user_e = user.replace("'", "''")
        pass_e = passwd.replace("'", "''")
        if user:
            cmd = (f"$n='{unc_e}'; $u='{user_e}'; $p='{pass_e}'; "
                   f"net use {letter}: $n $p /user:$u /persistent:yes 2>&1")
        else:
            cmd = f"$n='{unc_e}'; net use {letter}: $n /persistent:yes 2>&1"

        self._dm_status_lbl.configure(text=f"Mapping {letter}: → {unc} …", text_color=T.MUTED)

        def task():
            rc, out = run_inline_powershell(cmd)

            def done():
                if rc == 0 or "successfully" in out.lower():
                    self._dm_status_lbl.configure(
                        text=f"✓ {letter}: mapped to {unc}", text_color=T.OK)
                    self._dm_unc_entry.delete(0, "end")
                    self._dm_user_entry.delete(0, "end")
                    self._dm_pass_entry.delete(0, "end")
                    log(f"Mapped {letter}: → {unc}", "success")
                    self._append_output(f"Mapped {letter}: → {unc}")
                    self._dm_refresh()
                else:
                    err = out.strip()[:160]
                    self._dm_status_lbl.configure(text=f"Error: {err}", text_color=T.FAIL)
                    self._append_output(f"Map error: {err}")

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _dm_disconnect(self):
        selected = [(letter, unc) for letter, (var, unc) in self._dm_checkboxes.items() if var.get()]
        if not selected:
            self._dm_status_lbl.configure(
                text="Check at least one drive to disconnect.", text_color=T.FAIL)
            return
        cmds = " ; ".join(f"net use {letter} /delete /yes 2>&1" for letter, _ in selected)
        self._dm_status_lbl.configure(text="Disconnecting…", text_color=T.MUTED)

        def task():
            rc, out = run_inline_powershell(cmds)

            def done():
                names = ", ".join(l for l, _ in selected)
                if rc == 0:
                    self._dm_status_lbl.configure(
                        text=f"✓ Disconnected: {names}", text_color=T.OK)
                    log(f"Disconnected drives: {names}", "success")
                    self._append_output(f"Disconnected: {names}")
                else:
                    self._dm_status_lbl.configure(
                        text=f"Error/partial: {out.strip()[:80]}", text_color=T.WARN)
                self._dm_refresh()

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    # ── Helpers ───────────────────────────────────────────────────────

    def _append_output(self, text: str):
        self._log.append(text)
