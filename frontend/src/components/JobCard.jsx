import { motion } from "framer-motion";
import { MapPin, ExternalLink, Briefcase, TrendingUp } from "lucide-react";
import { useStore } from "../store/useStore";
import { useNavigate } from "react-router-dom";

export default function JobCard({ job }) {
  const { setSelectedJob } = useStore();
  const navigate           = useNavigate();

  if (!job) return null;

  const score   = job.match_score || 0;
  const isDemo  = job.source === "demo";

  const scoreColor =
    score >= 80 ? "#16A34A" :
    score >= 60 ? "#6B5CE7" :
    score >= 40 ? "#D97706" : "#DC2626";

  const scoreBg =
    score >= 80 ? "#DCFCE7" :
    score >= 60 ? "#E8E4FF" :
    score >= 40 ? "#FEF3C7" : "#FEE2E2";

  const circumference = 2 * Math.PI * 22;
  const dash = circumference * (score / 100);

  const handleTailorResume = () => {
    setSelectedJob(job);
    navigate("/rewrite");
  };

  return (
    <motion.div
      whileHover={{ scale: 1.015, borderColor: "#6B5CE7" }}
      whileTap={{ scale: 0.99 }}
      className="bg-white border border-[#E8E4FF] rounded-2xl p-5
                 shadow-[0_2px_12px_rgba(107,92,231,0.06)]
                 cursor-pointer transition-all flex flex-col h-full"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex-1 min-w-0">
          {/* Demo badge */}
          {isDemo && (
            <span className="inline-block px-2 py-0.5 bg-[#F0EEFF] text-[#6B5CE7]
                             text-[10px] font-semibold rounded-full mb-1.5">
              Demo
            </span>
          )}
          <h3 className="text-[14px] font-bold text-[#111] leading-tight mb-0.5 truncate">
            {job.title || "Software Engineer"}
          </h3>
          <p className="text-[13px] text-[#6B5CE7] font-semibold truncate">
            {job.company || "Company"}
          </p>
          {job.location && (
            <div className="flex items-center gap-1 mt-1">
              <MapPin className="w-3 h-3 text-[#BBB] shrink-0"/>
              <span className="text-[11px] text-[#888] truncate">{job.location}</span>
            </div>
          )}
          {job.salary && (
            <div className="flex items-center gap-1 mt-0.5">
              <TrendingUp className="w-3 h-3 text-[#BBB] shrink-0"/>
              <span className="text-[11px] text-[#888]">{job.salary}</span>
            </div>
          )}
        </div>

        {/* Score ring */}
        {score > 0 && (
          <div className="relative w-14 h-14 shrink-0">
            <svg viewBox="0 0 50 50" className="w-14 h-14 -rotate-90">
              <circle cx="25" cy="25" r="22"
                fill="none" stroke="#F0EEFF" strokeWidth="4"/>
              <motion.circle
                cx="25" cy="25" r="22"
                fill="none"
                stroke={scoreColor}
                strokeWidth="4"
                strokeLinecap="round"
                strokeDasharray={circumference}
                initial={{ strokeDashoffset: circumference }}
                animate={{ strokeDashoffset: circumference - dash }}
                transition={{ duration: 1, ease: "easeOut" }}
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-[11px] font-extrabold font-mono"
                style={{ color: scoreColor }}>
                {score}%
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Description */}
      {job.description && (
        <p className="text-[12px] text-[#888] leading-relaxed mb-3 line-clamp-2 flex-1">
          {job.description}
        </p>
      )}

      {/* Matched skills */}
      {job.matched_skills?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {job.matched_skills.slice(0, 4).map(skill => (
            <span key={skill}
              className="px-2 py-0.5 bg-[#E8E4FF] text-[#6B5CE7]
                         text-[10px] font-semibold rounded-full">
              ✓ {skill}
            </span>
          ))}
          {job.missing_skills?.slice(0, 2).map(skill => (
            <span key={skill}
              className="px-2 py-0.5 bg-[#FEF3C7] text-[#D97706]
                         text-[10px] font-semibold rounded-full">
              + {skill}
            </span>
          ))}
        </div>
      )}

      {/* Recommendation */}
      {job.recommendation && (
        <p className="text-[11px] text-[#888] italic mb-3 leading-relaxed">
          {job.recommendation}
        </p>
      )}

      {/* Actions */}
      <div className="flex gap-2 mt-auto pt-3 border-t border-[#F0EEFF]">
        <button
          onClick={handleTailorResume}
          className="flex-1 py-2 bg-gradient-to-r from-[#6B5CE7] to-[#8B7CF8]
                     rounded-lg text-[12px] font-bold text-white
                     hover:opacity-90 transition-opacity"
        >
          Tailor Resume
        </button>
        {job.apply_link && job.apply_link !== "#" ? (
          <a
            href={job.apply_link}
            target="_blank"
            rel="noreferrer"
            onClick={e => e.stopPropagation()}
            className="flex items-center gap-1 px-3 py-2 bg-white border border-[#E8E4FF]
                       rounded-lg text-[12px] font-semibold text-[#6B5CE7]
                       hover:bg-[#F0EEFF] transition-colors"
          >
            Apply <ExternalLink className="w-3 h-3"/>
          </a>
        ) : (
          <span className="flex items-center gap-1 px-3 py-2 bg-[#F0EEFF]
                           rounded-lg text-[12px] text-[#BBB]">
            <Briefcase className="w-3 h-3"/> Demo
          </span>
        )}
      </div>
    </motion.div>
  );
}
