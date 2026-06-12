import sys

with open('frontend2/app/quarter-car/page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

imports = '''// @ts-nocheck

"use client";
import { useState, useEffect, Suspense, useMemo } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import {
  Play, Settings2, AlertTriangle,
  Activity, Save, Sparkles, X, TrendingUp, BarChart3,
  Zap, GitBranch, Crosshair, RefreshCw,
} from "lucide-react";
import PDFExport from "../../components/PDFExport";
import DataExport from "../../components/DataExport";
import ComparePanel from "../../components/ComparePanel";
import VehiclePresets from "../../components/VehiclePresets";
import SimHistory, { saveSimulationToHistory } from "../../components/SimHistory";
import PlanGate from "../../components/PlanGate";
import DamperLUTInput from "../../components/DamperLUTInput";
import { useAuth } from "../../contexts/AuthContext";
import ISOReportExport from "../../components/ISOReportExport";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ROAD_PROFILES = [
  { label: "Step Input",        value: "step"    },
  { label: "Pothole",           value: "pothole" },
  { label: "Sine Wave",         value: "sine"    },
  { label: "Random (ISO 8608)", value: "random"  },
'''

start_idx = content.find('{ label: "Impulse"')
with open('frontend2/app/quarter-car/page.tsx', 'w', encoding='utf-8') as f:
    f.write(imports + content[start_idx:])
