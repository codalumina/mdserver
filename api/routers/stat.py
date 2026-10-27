"""
System Telemetry and Diagnostics Routing Module.

This module aggregates both MetaTrader 5 account statistics (balance, equity, 
ping) and physical server metrics (CPU load, RAM usage). It includes specialized 
logic to read Linux procfs metrics from within a WINE encapsulated environment.
"""

import os
import platform
import shutil
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status

from core.mt5_engine import engine
from core.logger import logger
from schemas.mt5 import ServerStatResponse, MT5Stats, OSStats

router = APIRouter()

@router.get("/", response_model=ServerStatResponse)
def server_stat():
    """
    Retrieve comprehensive MetaTrader 5 and physical server statistics.
    
    Forensic System Parsing: 
    When Python runs inside WINE, standard OS metric libraries (like psutil) 
    attempt to read Windows APIs that WINE may not fully implement. To bypass 
    this and get true server loads, this function directly parses the underlying 
    Linux `/proc` filesystem. Since WINE maps the Linux root to the `Z:/` drive, 
    the router intelligently falls back to `Z:/proc/meminfo` to guarantee accurate 
    telemetry without crashing.
    """
    
    try:
        terminal_info = engine.get_terminal_info()
        account_info = engine.get_account_info()

        total_positions = engine.get_positions_total()
        total_orders = engine.get_orders_total()

        account_name = account_info.get("name", "Unknown")
        name_initials = "".join([part[0] for part in account_name.split()]) if account_name else "Unknown"

        mt5_stats = MT5Stats(
            connected=terminal_info.get("connected", False),
            broker=account_info.get("company", "Unknown"),
            server=account_info.get("server", "Unknown"),
            account_name_initials=name_initials,
            leverage=account_info.get("leverage", 0),
            ping=terminal_info.get("ping_last", 0.0),
            build=terminal_info.get("build", 0),
            account_currency=account_info.get("currency", ""),
            balance=account_info.get("balance", 0.0),
            equity=account_info.get("equity", 0.0),
            floating_profit=account_info.get("profit", 0.0),
            margin_free=account_info.get("margin_free", 0.0),
            margin_level_pct=account_info.get("margin_level", 0.0),
            trade_allowed_by_broker=account_info.get("trade_allowed", False),
            algo_trading_allowed=terminal_info.get("trade_allowed", False),
            open_positions_count=total_positions,
            pending_orders_count=total_orders,
        )

        os_stats_dict = {
            "python_architecture": platform.architecture()[0],
            "wine_version": "Active" if "wine" in os.environ.get("WINEPREFIX", "").lower() else "Inactive"
        }

        # Safe cross-platform Linux / WINE proc metrics
        try:
            # WINE maps the Linux root to Z:/
            proc_prefix = "Z:/proc" if os.path.exists("Z:/proc") else "/proc"
            
            if os.path.exists(proc_prefix):
                with open(f"{proc_prefix}/meminfo", "r") as f:
                    meminfo = f.readlines()
                    total_mb = int(meminfo[0].split()[1]) / 1024
                    available_mb = int(meminfo[2].split()[1]) / 1024
                    os_stats_dict["ram_total_mb"] = round(total_mb, 2)
                    os_stats_dict["ram_available_mb"] = round(available_mb, 2)
                    os_stats_dict["ram_used_mb"] = round(total_mb - available_mb, 2)

                with open(f"{proc_prefix}/loadavg", "r") as f:
                    os_stats_dict["cpu_load_avg"] = f.read().split()[:3]

                with open(f"{proc_prefix}/uptime", "r") as f:
                    uptime_seconds = float(f.readline().split()[0])
                    os_stats_dict["uptime_days"] = round(uptime_seconds / 86400, 2)
                    os_stats_dict["uptime_hours"] = round(uptime_seconds / 3600, 2)

                with open(f"{proc_prefix}/cpuinfo", "r") as f:
                    cpuinfo = f.read()
                    os_stats_dict["cpu_cores"] = cpuinfo.count("processor\t:")
                    model_lines = [line for line in cpuinfo.split("\n") if "model name" in line]
                    os_stats_dict["cpu_model"] = model_lines[0].split(":")[1].strip() if model_lines else "Unknown CPU"

                # Check disk usage for the primary drive (Z:/ on WINE, / on Linux, C:/ on Windows)
                drive_target = "Z:/" if os.path.exists("Z:/") else ("/" if os.path.exists("/") else "C:/")
                disk = shutil.disk_usage(drive_target)
                os_stats_dict["disk_total_gb"] = round(disk.total / (1024**3), 2)
                os_stats_dict["disk_free_gb"] = round(disk.free / (1024**3), 2)
            else:
                os_stats_dict["linux_read_error"] = "Not available (Non-Linux/WINE environment)"

        except Exception as e:
            os_stats_dict["linux_read_error"] = f"Metric read failed: {str(e)}"

        return ServerStatResponse(
            status="healthy",
            timestamp=datetime.now(timezone.utc).isoformat(),
            mt5=mt5_stats,
            server=OSStats(**os_stats_dict)
        )

    except Exception as e:
        logger.error(f"Failed to compile server stats: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))