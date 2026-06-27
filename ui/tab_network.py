import re
import threading
import customtkinter as ctk
import tkinter.messagebox as msgbox
from modules.runner import run_inline_powershell
from modules.logger import log


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
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # --- Network Info ---
        net_frame = ctk.CTkFrame(scroll)
        net_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        net_frame.grid_columnconfigure(1, weight=1)
        net_frame.grid_columnconfigure(3, weight=1)

        net_hdr = ctk.CTkFrame(net_frame, fg_color="transparent")
        net_hdr.grid(row=0, column=0, columnspan=4, sticky="ew", padx=20, pady=(16, 8))
        net_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(net_hdr, text="Network Info",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w")
        self._net_toggle_btn = ctk.CTkButton(net_hdr, text="Disable Adapter", width=140,
                                              fg_color="#B71C1C", hover_color="#7f1111",
                                              command=self._toggle_adapter)
        self._net_toggle_btn.grid(row=0, column=1, sticky="e", padx=(0, 8))
        self._refresh_net_btn = ctk.CTkButton(net_hdr, text="Refresh", width=100,
                                               command=self._fetch_network_info)
        self._refresh_net_btn.grid(row=0, column=2, sticky="e")

        self._net_adapter_var = ctk.StringVar()
        self._net_adapter_menu = ctk.CTkOptionMenu(
            net_frame, variable=self._net_adapter_var, values=["—"],
            command=self._on_adapter_select, width=400)
        self._net_adapter_menu.grid(row=1, column=0, columnspan=4, padx=20, pady=(0, 6), sticky="w")
        self._net_adapter_menu.grid_remove()

        ctk.CTkLabel(net_frame, text="Adapter:").grid(row=2, column=0, padx=(20, 4), pady=5, sticky="w")
        self._net_adapter_entry = ctk.CTkEntry(net_frame, width=220)
        self._net_adapter_entry.grid(row=2, column=1, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(net_frame, text="IP Address:").grid(row=2, column=2, padx=(20, 4), pady=5, sticky="w")
        self._net_ip_entry = ctk.CTkEntry(net_frame, width=220)
        self._net_ip_entry.grid(row=2, column=3, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(net_frame, text="Subnet / Prefix:").grid(row=3, column=0, padx=(20, 4), pady=5, sticky="w")
        self._net_subnet_entry = ctk.CTkEntry(net_frame, width=220)
        self._net_subnet_entry.grid(row=3, column=1, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(net_frame, text="Gateway:").grid(row=3, column=2, padx=(20, 4), pady=5, sticky="w")
        self._net_gw_entry = ctk.CTkEntry(net_frame, width=220)
        self._net_gw_entry.grid(row=3, column=3, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(net_frame, text="DNS Servers:").grid(row=4, column=0, padx=(20, 4), pady=5, sticky="w")
        self._net_dns_entry = ctk.CTkEntry(net_frame, width=220)
        self._net_dns_entry.grid(row=4, column=1, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(net_frame, text="MAC Address:").grid(row=4, column=2, padx=(20, 4), pady=5, sticky="w")
        self._net_mac_entry = ctk.CTkEntry(net_frame, width=220)
        self._net_mac_entry.grid(row=4, column=3, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(net_frame,
                     text="Edit IP / Gateway / DNS above, then click Apply Static IP  —  or reset to DHCP.",
                     text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=5, column=0, columnspan=4, padx=20, pady=(4, 4), sticky="w")

        net_btn_row = ctk.CTkFrame(net_frame, fg_color="transparent")
        net_btn_row.grid(row=6, column=0, columnspan=4, padx=20, pady=(0, 16), sticky="w")
        self._apply_ip_btn = ctk.CTkButton(net_btn_row, text="Apply Static IP", width=150,
                                            command=self._apply_static_ip)
        self._apply_ip_btn.grid(row=0, column=0, padx=(0, 8))
        self._set_dhcp_btn = ctk.CTkButton(net_btn_row, text="Set to DHCP", width=130,
                                            fg_color="#2e7d32", hover_color="#1b5e20",
                                            command=self._set_dhcp)
        self._set_dhcp_btn.grid(row=0, column=1)

        # Output
        ctk.CTkLabel(scroll, text="Output",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=1, column=0, padx=20, pady=(10, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(scroll, height=140, state="disabled")
        self.output_box.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="ew")

        self.after(300, self._fetch_network_info)

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
            text="Disable Adapter" if is_up else "Enable Adapter",
            fg_color="#B71C1C" if is_up else "#1565C0",
            hover_color="#7f1111" if is_up else "#0d3c6e",
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

    # ── Helpers ───────────────────────────────────────────────────────

    def _append_output(self, text: str):
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")
