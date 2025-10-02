"""
SNMP Switch Port Monitor
Pro pysnmp 6.2.6 s Python 3.12
S grafickým zobrazením trafficu
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
from datetime import datetime
from collections import deque

# Import pro pysnmp 6.2.6 - funkce jsou v v3arch!
from pysnmp.hlapi.v3arch import (
    get_cmd, next_cmd, walk_cmd,
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity
)

class SNMPMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("SNMP Port Monitor (pysnmp 6.2.6)")
        self.root.geometry("1000x650")
        
        self.monitoring = False
        self.interfaces = {}
        self.prev_stats = {}
        self.start_time = None
        self.debug_mode = False  # Debug režim
        
        # Min/Max hodnoty
        self.rx_min = float('inf')
        self.rx_max = 0
        self.tx_min = float('inf')
        self.tx_max = 0
        
        # SNMP OID konstanty
        self.OID = {
            'sysDescr': '1.3.6.1.2.1.1.1.0',
            'ifDescr': '1.3.6.1.2.1.2.2.1.2',
            'ifAlias': '1.3.6.1.2.1.31.1.1.1.18',
            'ifAdminStatus': '1.3.6.1.2.1.2.2.1.7',
            'ifOperStatus': '1.3.6.1.2.1.2.2.1.8',
            # High-capacity 64-bit countery (ifXTable)
            'ifHCInOctets': '1.3.6.1.2.1.31.1.1.1.6',
            'ifHCOutOctets': '1.3.6.1.2.1.31.1.1.1.10',
            'ifHCInUcastPkts': '1.3.6.1.2.1.31.1.1.1.7',
            'ifHCOutUcastPkts': '1.3.6.1.2.1.31.1.1.1.11',
            # Standardní countery pro errors (nemají HC verzi)
            'ifInErrors': '1.3.6.1.2.1.2.2.1.14',
            'ifOutErrors': '1.3.6.1.2.1.2.2.1.20',
        }
        
        self.setup_ui()
        self.log("✅ pysnmp 6.2.6 načten úspěšně")
        self.log("📝 Zadejte IP a community, pak klikněte TEST")
        
    def setup_ui(self):
        # === KONFIGURACE ===
        conf = ttk.LabelFrame(self.root, text="  Konfigurace  ", padding=15)
        conf.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(conf, text="IP switche:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.ip = ttk.Entry(conf, width=18, font=("Arial", 11))
        self.ip.grid(row=0, column=1, padx=5, pady=5)
        self.ip.insert(0, "192.168.1.1")
        
        ttk.Label(conf, text="Community:", font=("Arial", 10, "bold")).grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.community = ttk.Entry(conf, width=12, font=("Arial", 11))
        self.community.grid(row=0, column=3, padx=5, pady=5)
        self.community.insert(0, "public")
        
        ttk.Label(conf, text="SNMP:", font=("Arial", 10, "bold")).grid(row=0, column=4, sticky="w", padx=5, pady=5)
        self.version = ttk.Combobox(conf, width=6, values=["v1", "v2c"], state="readonly", font=("Arial", 11))
        self.version.grid(row=0, column=5, padx=5, pady=5)
        self.version.current(1)
        
        ttk.Label(conf, text="Port:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.port_combo = ttk.Combobox(conf, width=80, state="readonly", font=("Arial", 9))
        self.port_combo.grid(row=1, column=1, columnspan=5, padx=5, pady=5, sticky="ew")
        
        # === TLAČÍTKA ===
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(btn_frame, text="🔍 TEST připojení", command=self.test, width=20).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="📋 Načíst porty", command=self.load_ports, width=20).pack(side="left", padx=3)
        
        self.start_btn = ttk.Button(btn_frame, text="▶ START", command=self.start, state="disabled", width=15)
        self.start_btn.pack(side="left", padx=3)
        
        self.stop_btn = ttk.Button(btn_frame, text="■ STOP", command=self.stop, state="disabled", width=15)
        self.stop_btn.pack(side="left", padx=3)
        
        ttk.Button(btn_frame, text="🗑 Vymazat", command=self.clear, width=12).pack(side="right", padx=3)
        
        self.debug_check = ttk.Checkbutton(btn_frame, text="🐛 Debug", command=self.toggle_debug)
        self.debug_check.pack(side="right", padx=3)
        
        # === HLAVNÍ KONTEJNER ===
        main_container = ttk.Frame(self.root)
        main_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # === DISPLEJE (nahoře) ===
        display_frame = ttk.LabelFrame(main_container, text="  📊 Real-time Traffic  ", padding=15)
        display_frame.pack(side="top", fill="both", expand=False, pady=(0, 5))
        
        display_container = ttk.Frame(display_frame)
        display_container.pack(fill="both", expand=True)
        
        # RX Display (vlevo)
        rx_frame = ttk.Frame(display_container, relief="solid", borderwidth=2)
        rx_frame.pack(side="left", expand=True, fill="both", padx=10, pady=5)
        
        ttk.Label(rx_frame, text="⬇ DOWNLOAD (RX)", font=("Arial", 14, "bold"), foreground="#00aa00").pack(pady=5)
        self.rx_speed_label = ttk.Label(rx_frame, text="0.00 Mbps", font=("Arial", 32, "bold"), foreground="#00ff00")
        self.rx_speed_label.pack(pady=10)
        self.rx_pps_label = ttk.Label(rx_frame, text="0 pkt/s", font=("Arial", 16), foreground="#88ff88")
        self.rx_pps_label.pack(pady=5)
        
        # Min/Max pro RX
        rx_minmax_frame = ttk.Frame(rx_frame)
        rx_minmax_frame.pack(pady=5)
        self.rx_min_label = ttk.Label(rx_minmax_frame, text="Min: -", font=("Arial", 10), foreground="#666666")
        self.rx_min_label.pack(side="left", padx=10)
        self.rx_max_label = ttk.Label(rx_minmax_frame, text="Max: -", font=("Arial", 10), foreground="#666666")
        self.rx_max_label.pack(side="left", padx=10)
        
        # TX Display (vpravo)
        tx_frame = ttk.Frame(display_container, relief="solid", borderwidth=2)
        tx_frame.pack(side="left", expand=True, fill="both", padx=10, pady=5)
        
        ttk.Label(tx_frame, text="⬆ UPLOAD (TX)", font=("Arial", 14, "bold"), foreground="#0088aa").pack(pady=5)
        self.tx_speed_label = ttk.Label(tx_frame, text="0.00 Mbps", font=("Arial", 32, "bold"), foreground="#00aaff")
        self.tx_speed_label.pack(pady=10)
        self.tx_pps_label = ttk.Label(tx_frame, text="0 pkt/s", font=("Arial", 16), foreground="#88ccff")
        self.tx_pps_label.pack(pady=5)
        
        # Min/Max pro TX
        tx_minmax_frame = ttk.Frame(tx_frame)
        tx_minmax_frame.pack(pady=5)
        self.tx_min_label = ttk.Label(tx_minmax_frame, text="Min: -", font=("Arial", 10), foreground="#666666")
        self.tx_min_label.pack(side="left", padx=10)
        self.tx_max_label = ttk.Label(tx_minmax_frame, text="Max: -", font=("Arial", 10), foreground="#666666")
        self.tx_max_label.pack(side="left", padx=10)
        
        # Čítače (vpravo)
        counters_frame = ttk.LabelFrame(display_container, text="  Counters  ", padding=10)
        counters_frame.pack(side="left", fill="both", expand=False, padx=10)
        
        # Tabulka čítačů
        counter_style = ("Consolas", 10)
        
        ttk.Label(counters_frame, text="RX Errors:", font=counter_style, foreground="#ff6666").grid(row=0, column=0, sticky="w", pady=3)
        self.rx_errors_label = ttk.Label(counters_frame, text="0", font=("Consolas", 10, "bold"), foreground="#ff6666")
        self.rx_errors_label.grid(row=0, column=1, sticky="e", padx=10, pady=3)
        
        ttk.Label(counters_frame, text="TX Errors:", font=counter_style, foreground="#ff6666").grid(row=1, column=0, sticky="w", pady=3)
        self.tx_errors_label = ttk.Label(counters_frame, text="0", font=("Consolas", 10, "bold"), foreground="#ff6666")
        self.tx_errors_label.grid(row=1, column=1, sticky="e", padx=10, pady=3)
        
        ttk.Separator(counters_frame, orient="horizontal").grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        
        ttk.Label(counters_frame, text="RX Total:", font=counter_style, foreground="#66ff66").grid(row=3, column=0, sticky="w", pady=3)
        self.rx_packets_label = ttk.Label(counters_frame, text="0", font=("Consolas", 10, "bold"), foreground="#66ff66")
        self.rx_packets_label.grid(row=3, column=1, sticky="e", padx=10, pady=3)
        
        ttk.Label(counters_frame, text="TX Total:", font=counter_style, foreground="#66aaff").grid(row=4, column=0, sticky="w", pady=3)
        self.tx_packets_label = ttk.Label(counters_frame, text="0", font=("Consolas", 10, "bold"), foreground="#66aaff")
        self.tx_packets_label.grid(row=4, column=1, sticky="e", padx=10, pady=3)
        
        ttk.Separator(counters_frame, orient="horizontal").grid(row=5, column=0, columnspan=2, sticky="ew", pady=5)
        
        ttk.Label(counters_frame, text="Uptime:", font=counter_style, foreground="#ffff66").grid(row=6, column=0, sticky="w", pady=3)
        self.uptime_label = ttk.Label(counters_frame, text="00:00:00", font=("Consolas", 10, "bold"), foreground="#ffff66")
        self.uptime_label.grid(row=6, column=1, sticky="e", padx=10, pady=3)
        
        # === VÝSTUP (dole) ===
        out_frame = ttk.LabelFrame(main_container, text="  📝 Log  ", padding=10)
        out_frame.pack(side="bottom", fill="both", expand=True)
        
        self.output = scrolledtext.ScrolledText(
            out_frame, height=15, font=("Consolas", 9),
            bg="#0a0a0a", fg="#00ff00", insertbackground="white"
        )
        self.output.pack(fill="both", expand=True)
        
    def log(self, msg):
        self.output.insert(tk.END, msg + "\n")
        self.output.see(tk.END)
        self.root.update()
        
    def toggle_debug(self):
        """Přepne debug režim"""
        self.debug_mode = not self.debug_mode
        if self.debug_mode:
            self.log("🐛 DEBUG režim ZAPNUT")
        else:
            self.log("🐛 DEBUG režim VYPNUT")
    
    def clear(self):
        self.output.delete(1.0, tk.END)
    
    def snmp_get(self, oid):
        """SNMP GET request"""
        try:
            import asyncio
            
            async def do_get():
                target = await UdpTransportTarget.create((self.ip.get(), 161))
                return await get_cmd(
                    SnmpEngine(),
                    CommunityData(self.community.get(), mpModel=0 if self.version.get() == "v1" else 1),
                    target,
                    ContextData(),
                    ObjectType(ObjectIdentity(oid))
                )
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            errorIndication, errorStatus, errorIndex, varBinds = loop.run_until_complete(do_get())
            loop.close()
            
            if errorIndication:
                return None, str(errorIndication)
            elif errorStatus:
                return None, f"{errorStatus.prettyPrint()} at {errorIndex}"
            else:
                return str(varBinds[0][1]), None
                
        except Exception as e:
            return None, str(e)
    
    def snmp_walk(self, oid):
        """SNMP WALK request"""
        results = {}
        try:
            import asyncio
            
            async def do_walk():
                target = await UdpTransportTarget.create((self.ip.get(), 161))
                data = []
                async for errorIndication, errorStatus, errorIndex, varBinds in walk_cmd(
                    SnmpEngine(),
                    CommunityData(self.community.get(), mpModel=0 if self.version.get() == "v1" else 1),
                    target,
                    ContextData(),
                    ObjectType(ObjectIdentity(oid)),
                    lexicographicMode=False
                ):
                    data.append((errorIndication, errorStatus, errorIndex, varBinds))
                return data
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(do_walk())
            loop.close()
            
            for errorIndication, errorStatus, errorIndex, varBinds in data:
                if errorIndication:
                    return None, str(errorIndication)
                elif errorStatus:
                    return None, f"{errorStatus.prettyPrint()}"
                else:
                    for varBind in varBinds:
                        oid_str = str(varBind[0])
                        index = oid_str.split('.')[-1]
                        value = str(varBind[1])
                        results[index] = value
            
            return results, None
            
        except Exception as e:
            return None, str(e)
    
    def test(self):
        """Test SNMP připojení"""
        self.clear()
        self.log("=" * 90)
        self.log("🔍 TEST SNMP PŘIPOJENÍ")
        self.log("=" * 90)
        self.log(f"📡 IP: {self.ip.get()}")
        self.log(f"🔑 Community: {self.community.get()}")
        self.log(f"📋 Verze: {self.version.get()}")
        self.log("")
        self.log("⏳ Připojuji se...")
        
        result, error = self.snmp_get(self.OID['sysDescr'])
        
        if error:
            self.log("")
            self.log("❌ PŘIPOJENÍ SELHALO")
            self.log(f"Chyba: {error}")
            self.log("")
            self.log("🔧 Zkontrolujte:")
            self.log("  • IP adresu switche")
            self.log("  • SNMP community")
            self.log("  • SNMP je povoleno na zařízení")
            self.log("  • Firewall neblokuje port 161/UDP")
            messagebox.showerror("Chyba", f"SNMP selhalo:\n{error}")
        else:
            self.log("")
            self.log("✅✅✅ ÚSPĚCH! ✅✅✅")
            self.log("")
            self.log("📦 Zařízení:")
            self.log(f"   {result[:200]}")
            self.log("")
            self.log("➡ Nyní klikněte na 'Načíst porty'")
            messagebox.showinfo("Úspěch! 🎉", "SNMP připojení funguje!")
    
    def load_ports(self):
        """Načtení portů"""
        self.clear()
        self.log("=" * 90)
        self.log("📋 NAČÍTÁNÍ PORTŮ")
        self.log("=" * 90)
        self.log("")
        self.log("⏳ Načítám seznam portů...")
        
        # Načti názvy portů
        if_names, error = self.snmp_walk(self.OID['ifDescr'])
        
        if error:
            self.log("")
            self.log(f"❌ Chyba: {error}")
            messagebox.showerror("Chyba", f"Nepodařilo se načíst porty:\n{error}")
            return
        
        if not if_names:
            self.log("❌ Žádné porty nenalezeny")
            messagebox.showwarning("Upozornění", "Nenalezeny žádné porty")
            return
        
        # Načti statusy
        self.log(f"⏳ Načítám statusy a popisy {len(if_names)} portů...")
        if_admin, _ = self.snmp_walk(self.OID['ifAdminStatus'])
        if_oper, _ = self.snmp_walk(self.OID['ifOperStatus'])
        if_alias, _ = self.snmp_walk(self.OID['ifAlias'])
        
        self.log("")
        self.interfaces = {}
        ports = []
        
        for idx, name in if_names.items():
            admin = if_admin.get(idx, '2') if if_admin else '2'
            oper = if_oper.get(idx, '2') if if_oper else '2'
            alias = if_alias.get(idx, '') if if_alias else ''
            
            status = []
            status.append('UP' if admin == '1' else 'DOWN')
            status.append('active' if oper == '1' else 'inactive')
            status_str = f"[{'/'.join(status)}]"
            
            self.interfaces[idx] = name
            
            # Formát: "1: InLoopBack0 - Popis portu [UP/active]"
            if alias and alias.strip():
                display_text = f"{idx}: {name} - {alias} {status_str}"
            else:
                display_text = f"{idx}: {name} {status_str}"
            
            ports.append(display_text)
            self.log(f"  {display_text}")
        
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)
            self.start_btn.config(state="normal")
        
        self.log("")
        self.log(f"✅ Načteno {len(ports)} portů")
        self.log("")
        self.log("➡ Vyberte port a klikněte START")
        messagebox.showinfo("Hotovo", f"Načteno {len(ports)} portů!")
    
    def get_stats(self, idx):
        """Získá statistiky pro port - používá high-capacity 64-bit countery"""
        stats = {}
        
        val, _ = self.snmp_get(f"{self.OID['ifHCInOctets']}.{idx}")
        stats['in_octets'] = int(val) if val and val.isdigit() else 0
        
        val, _ = self.snmp_get(f"{self.OID['ifHCOutOctets']}.{idx}")
        stats['out_octets'] = int(val) if val and val.isdigit() else 0
        
        val, _ = self.snmp_get(f"{self.OID['ifHCInUcastPkts']}.{idx}")
        stats['in_packets'] = int(val) if val and val.isdigit() else 0
        
        val, _ = self.snmp_get(f"{self.OID['ifHCOutUcastPkts']}.{idx}")
        stats['out_packets'] = int(val) if val and val.isdigit() else 0
        
        val, _ = self.snmp_get(f"{self.OID['ifInErrors']}.{idx}")
        stats['in_errors'] = int(val) if val and val.isdigit() else 0
        
        val, _ = self.snmp_get(f"{self.OID['ifOutErrors']}.{idx}")
        stats['out_errors'] = int(val) if val and val.isdigit() else 0
        
        return stats
    
    def format_speed_mbps(self, bytes_per_sec):
        """Formátuje rychlost v Mbps/Gbps"""
        mbps = (bytes_per_sec * 8) / (1000 * 1000)  # Bajty -> Megabity
        
        if mbps >= 3000:
            gbps = mbps / 1000
            return f"{gbps:.2f} Gbps"
        else:
            return f"{mbps:.2f} Mbps"
    
    def update_displays(self, in_rate, out_rate, in_pps, out_pps):
        """Aktualizuje textové displeje"""
        # Aktualizuj min/max
        if in_rate > 0:  # Ignoruj nulové hodnoty
            self.rx_min = min(self.rx_min, in_rate)
            self.rx_max = max(self.rx_max, in_rate)
        
        if out_rate > 0:  # Ignoruj nulové hodnoty
            self.tx_min = min(self.tx_min, out_rate)
            self.tx_max = max(self.tx_max, out_rate)
        
        # Rychlost
        self.rx_speed_label.config(text=self.format_speed_mbps(in_rate))
        self.tx_speed_label.config(text=self.format_speed_mbps(out_rate))
        
        # Pakety za sekundu
        self.rx_pps_label.config(text=f"{int(in_pps):,} pkt/s")
        self.tx_pps_label.config(text=f"{int(out_pps):,} pkt/s")
        
        # Min/Max
        if self.rx_min != float('inf'):
            self.rx_min_label.config(text=f"Min: {self.format_speed_mbps(self.rx_min)}")
            self.rx_max_label.config(text=f"Max: {self.format_speed_mbps(self.rx_max)}")
        
        if self.tx_min != float('inf'):
            self.tx_min_label.config(text=f"Min: {self.format_speed_mbps(self.tx_min)}")
            self.tx_max_label.config(text=f"Max: {self.format_speed_mbps(self.tx_max)}")
        
        # Aktualizuj čítače
        if self.prev_stats:
            self.rx_errors_label.config(text=f"{self.prev_stats.get('in_errors', 0):,}")
            self.tx_errors_label.config(text=f"{self.prev_stats.get('out_errors', 0):,}")
            self.rx_packets_label.config(text=f"{self.prev_stats.get('in_packets', 0):,}")
            self.tx_packets_label.config(text=f"{self.prev_stats.get('out_packets', 0):,}")
            
            # Uptime
            if self.start_time:
                elapsed = time.time() - self.start_time
                hours = int(elapsed // 3600)
                minutes = int((elapsed % 3600) // 60)
                seconds = int(elapsed % 60)
                self.uptime_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    
    def format_speed_short(self, bytes_per_sec):
        """Krátký formát rychlosti"""
        val = bytes_per_sec
        for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if val < 1024:
                return f"{val:.1f} {unit}"
            val /= 1024
        return f"{val:.1f} TB/s"
        """Formátuje rychlost"""
        # Bajty
        val = bytes_per_sec
        for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if val < 1024:
                bytes_str = f"{val:>7.2f} {unit}"
                break
            val /= 1024
        else:
            bytes_str = f"{val:>7.2f} TB/s"
        
        # Bity
        val = bytes_per_sec * 8
        for unit in ['bps', 'Kbps', 'Mbps', 'Gbps']:
            if val < 1000:
                bits_str = f"{val:>7.2f} {unit}"
                break
            val /= 1000
        else:
            bits_str = f"{val:>7.2f} Tbps"
        
        return f"{bytes_str} | {bits_str}"
    
    def monitor_loop(self):
        """Monitoring loop"""
        sel = self.port_combo.get()
        idx = sel.split(':')[0].strip()
        name = self.interfaces[idx]
        
        self.output.delete(1.0, tk.END)
        self.log("=" * 50)
        self.log(f"🎯 MONITORING")
        self.log(f"Port: {name}")
        self.log(f"Index: {idx}")
        self.log("=" * 50)
        self.log("")
        
        # Vymažeme historii
        self.start_time = time.time()
        
        # Reset min/max hodnot
        self.rx_min = float('inf')
        self.rx_max = 0
        self.tx_min = float('inf')
        self.tx_max = 0
        
        interval = 2
        last_measurement_time = time.time()
        
        while self.monitoring:
            try:
                current_time = time.time()
                stats = self.get_stats(idx)
                ts = datetime.now().strftime("%H:%M:%S")
                
                if self.prev_stats:
                    # Skutečný interval mezi měřeními
                    actual_interval = current_time - last_measurement_time
                    
                    in_rate = (stats['in_octets'] - self.prev_stats['in_octets']) / actual_interval
                    out_rate = (stats['out_octets'] - self.prev_stats['out_octets']) / actual_interval
                    in_pps = (stats['in_packets'] - self.prev_stats['in_packets']) / actual_interval
                    out_pps = (stats['out_packets'] - self.prev_stats['out_packets']) / actual_interval
                    
                    # Debug výpis
                    if self.debug_mode:
                        self.log(f"[{ts}] DEBUG:")
                        self.log(f"  Current IN octets:  {stats['in_octets']:,}")
                        self.log(f"  Previous IN octets: {self.prev_stats['in_octets']:,}")
                        self.log(f"  Delta IN octets:    {stats['in_octets'] - self.prev_stats['in_octets']:,}")
                        self.log(f"  IN bytes/sec:       {in_rate:,.2f}")
                        self.log(f"  IN Mbps calc:       {(in_rate * 8) / (1000 * 1000):.2f}")
                        self.log(f"")
                        self.log(f"  Current OUT octets:  {stats['out_octets']:,}")
                        self.log(f"  Previous OUT octets: {self.prev_stats['out_octets']:,}")
                        self.log(f"  Delta OUT octets:    {stats['out_octets'] - self.prev_stats['out_octets']:,}")
                        self.log(f"  OUT bytes/sec:       {out_rate:,.2f}")
                        self.log(f"  OUT Mbps calc:       {(out_rate * 8) / (1000 * 1000):.2f}")
                        self.log(f"  Actual interval:     {actual_interval:.2f} sec (not {interval}!)")
                        self.log("")
                    
                    # Aktualizuj displeje
                    self.update_displays(max(0, in_rate), max(0, out_rate), max(0, in_pps), max(0, out_pps))
                    
                    # Log - teď v Mbps
                    if not self.debug_mode:  # Normální výpis jen když není debug
                        self.log(f"[{ts}]")
                        self.log(f"  ⬇ IN:  {self.format_speed_mbps(max(0, in_rate))}")
                        self.log(f"         {max(0, in_pps):>8.0f} pkt/s")
                        self.log(f"  ⬆ OUT: {self.format_speed_mbps(max(0, out_rate))}")
                        self.log(f"         {max(0, out_pps):>8.0f} pkt/s")
                    
                    if stats['in_errors'] > 0 or stats['out_errors'] > 0:
                        self.log(f"  ⚠ Errors: IN={stats['in_errors']}, OUT={stats['out_errors']}")
                    
                    self.log("-" * 50)
                
                self.prev_stats = stats
                last_measurement_time = current_time
                time.sleep(interval)
                
            except Exception as e:
                self.log(f"⚠ Chyba: {e}")
                time.sleep(interval)
    
    def start(self):
        """Start monitoring"""
        if not self.port_combo.get():
            messagebox.showwarning("Upozornění", "Vyberte port!")
            return
        
        self.monitoring = True
        self.prev_stats = {}
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.port_combo.config(state="disabled")
        
        thread = threading.Thread(target=self.monitor_loop, daemon=True)
        thread.start()
    
    def stop(self):
        """Stop monitoring"""
        self.monitoring = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.port_combo.config(state="readonly")
        self.log("")
        self.log("⏹ Monitoring zastaven")
        self.log("")

if __name__ == "__main__":
    root = tk.Tk()
    app = SNMPMonitor(root)
    root.mainloop()
