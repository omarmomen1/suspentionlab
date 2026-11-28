"use client";

import React, { useState } from "react";
import { CheckCircle2, XCircle, Clock, ShieldCheck, Hash, UserCheck, ShieldAlert } from "lucide-react";
import { DigitalTwinApi } from "../../lib/api_client";
import { useAuth } from "../../contexts/AuthContext";
import EngineeringErrorDisplay, { EngineeringErrorDisplayProps } from "./EngineeringErrorDisplay";

export type ApprovalStatusType = "APPROVED" | "REJECTED" | "PROPOSED" | "PENDING";

interface ApprovalStateProps {
  proposalId: string;
  status: ApprovalStatusType | string;
  approvedByRole?: string;
  approvedAt?: string;
  approvalSignature?: string;
  proposalHash?: string;
  onStatusChange?: (newStatus: "APPROVED" | "REJECTED") => void;
  className?: string;
}

export default function ApprovalState({
  proposalId,
  status,
  approvedByRole,
  approvedAt,
  approvalSignature,
  proposalHash,
  onStatusChange,
  className = "",
}: ApprovalStateProps) {
  const { user, can } = useAuth();
  const [loading, setLoading] = useState(false);
  const [currentStatus, setCurrentStatus] = useState(status);
  const [sig, setSig] = useState(approvalSignature);
  const [errorState, setErrorState] = useState<EngineeringErrorDisplayProps | null>(null);

  const canApprove = can("setup:approve");

  const handleAction = async (newStatus: "APPROVED" | "REJECTED") => {
    setLoading(true);
    setErrorState(null);
    try {
      const res = await DigitalTwinApi.setProposalStatus(proposalId, newStatus);
      setCurrentStatus(res.status);
      if (res.approval_signature) setSig(res.approval_signature);
      if (onStatusChange) onStatusChange(newStatus);
    } catch (err: any) {
      const errMsg = err?.message || String(err);
      const is403 = errMsg.includes("403") || errMsg.toLowerCase().includes("permission denied") || errMsg.toLowerCase().includes("lacks required capability");
      const is429 = errMsg.includes("429") || errMsg.toLowerCase().includes("rate limit");

      setErrorState({
        title: is403 ? "UNAUTHORIZED APPROVAL ATTEMPT" : (is429 ? "APPROVAL RATE LIMIT REACHED" : "APPROVAL ACTION FAILED"),
        whatFailed: `Submission of ${newStatus === "APPROVED" ? "cryptographic approval sign-off" : "proposal rejection"} for ${proposalId}`,
        why: is403
          ? `Authenticated user (${user?.email || "anonymous"}, role: ${user?.team_role || user?.org_role || "Member"}) lacks the 'setup:approve' capability. Least-privilege enterprise policy enforces that only Lead Engineers, Dynamics Leads, or Enterprise Admins can approve track releases.`
          : (is429
            ? "Authentication or request rate limit exceeded. The server throttled excessive requests."
            : errMsg),
        whatRemainsValid: "Candidate simulation evaluations, baseline vehicle parameters, and proposed parameter deltas remain intact, valid, and fully auditable.",
        whatCannotBeClaimed: "This setup cannot be claimed as signed-off, released for physical track use, or merged into vehicle baseline.",
        nextAction: is403
          ? "Switch to or request sign-off from an authorized approver (Lead Dynamics Engineer, Chief Engineer, or Enterprise Admin)."
          : "Wait a few moments and retry the sign-off action.",
        onDismiss: () => setErrorState(null),
      });
    } finally {
      setLoading(false);
    }
  };

  const isApproved = currentStatus === "APPROVED";
  const isRejected = currentStatus === "REJECTED";

  return (
    <div
      data-testid="approval-state-container"
      className={`p-4 rounded-2xl border font-mono text-xs ${
        isApproved
          ? "bg-emerald-950/20 border-emerald-500/40 text-emerald-300"
          : isRejected
          ? "bg-rose-950/20 border-rose-500/40 text-rose-300"
          : "bg-white/[0.02] border-white/[0.08] text-gray-300"
      } ${className}`}
    >
      {/* Top row: Status Badge & Approver Role */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div data-testid="approval-status-badge" className="flex items-center gap-1.5 font-bold uppercase tracking-wider">
          {isApproved ? (
            <>
              <CheckCircle2 size={15} className="text-emerald-400" />
              <span className="text-emerald-400 font-extrabold">APPROVED FOR TRACK USE</span>
            </>
          ) : isRejected ? (
            <>
              <XCircle size={15} className="text-rose-400" />
              <span className="text-rose-400 font-extrabold">REJECTED BY ENGINEERING</span>
            </>
          ) : (
            <>
              <Clock size={15} className="text-signal" />
              <span className="text-signal font-extrabold">PENDING SIGN-OFF</span>
            </>
          )}
        </div>

        {approvedByRole && (
          <div className="flex items-center gap-1 text-xs text-gray-400">
            <UserCheck size={12} />
            <span>Role: {approvedByRole}</span>
          </div>
        )}
      </div>

      {/* Signature & Timestamp */}
      <div className="space-y-1 text-xs text-gray-400">
        {approvedAt && (
          <div>
            Signed-off: <span className="text-white">{new Date(approvedAt).toLocaleString()}</span>
          </div>
        )}
        {sig && (
          <div className="flex items-center gap-1 text-xs text-zinc-400 truncate" data-testid="approval-hmac-signature">
            <ShieldCheck size={11} className="text-emerald-400 shrink-0" />
            <span>HMAC Sig:</span>
            <span className="font-mono text-gray-400 truncate">{sig}</span>
          </div>
        )}
        {proposalHash && (
          <div className="flex items-center gap-1 text-xs text-zinc-400 truncate">
            <Hash size={11} className="shrink-0" />
            <span>Hash:</span>
            <span className="font-mono text-gray-400 truncate">{proposalHash}</span>
          </div>
        )}
      </div>

      {/* Decision Actions for Pending Proposals */}
      {!isApproved && !isRejected && (
        <div className="mt-3 pt-3 border-t border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="text-xs text-gray-400 flex items-center gap-1">
            {!canApprove && (
              <span className="text-amber-400 font-sans flex items-center gap-1">
                <ShieldAlert size={12} /> Requires &apos;setup:approve&apos; capability
              </span>
            )}
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              data-testid="btn-reject-signoff"
              onClick={() => handleAction("REJECTED")}
              disabled={loading}
              className="px-3 py-1.5 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/40 text-rose-300 font-bold transition-all disabled:opacity-50"
            >
              Reject Proposal
            </button>
            <button
              data-testid="btn-approve-signoff"
              onClick={() => handleAction("APPROVED")}
              disabled={loading}
              className="px-4 py-1.5 rounded-lg bg-signal text-carbon font-bold hover:brightness-110 transition-all disabled:opacity-50 shadow-[0_0_12px_rgba(242,169,0,0.2)]"
            >
              Approve & Sign-Off
            </button>
          </div>
        </div>
      )}

      {/* Render 5-Section Engineering Failure UX Display */}
      {errorState && (
        <div className="mt-4 pt-3 border-t border-rose-500/20">
          <EngineeringErrorDisplay {...errorState} />
        </div>
      )}
    </div>
  );
}
