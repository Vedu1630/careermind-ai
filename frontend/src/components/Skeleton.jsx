import React from 'react';

export function SkeletonCard({ lines = 3 }) {
  return (
    <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5 animate-pulse">
      <div className="h-4 bg-[#F0EEFF] rounded-lg w-3/4 mb-3"/>
      {Array.from({length: lines}).map((_, i) => (
        <div key={i}
          className={`h-3 bg-[#F0EEFF] rounded mb-2 ${
            i === lines-1 ? "w-1/2" : "w-full"
          }`}
        />
      ))}
    </div>
  );
}

export function SkeletonJobCard() {
  return (
    <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5
                    animate-pulse shadow-[0_2px_12px_rgba(107,92,231,0.04)]">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex-1">
          <div className="h-3.5 bg-[#F0EEFF] rounded-lg w-3/4 mb-2"/>
          <div className="h-3 bg-[#F0EEFF] rounded w-1/2 mb-1.5"/>
          <div className="h-2.5 bg-[#F0EEFF] rounded w-2/5"/>
        </div>
        <div className="w-14 h-14 rounded-full bg-[#F0EEFF] shrink-0"/>
      </div>
      <div className="space-y-1.5 mb-4">
        <div className="h-2.5 bg-[#F0EEFF] rounded w-full"/>
        <div className="h-2.5 bg-[#F0EEFF] rounded w-5/6"/>
      </div>
      <div className="flex gap-1.5 mb-4">
        <div className="h-5 w-16 bg-[#F0EEFF] rounded-full"/>
        <div className="h-5 w-16 bg-[#F0EEFF] rounded-full"/>
        <div className="h-5 w-14 bg-[#F0EEFF] rounded-full"/>
      </div>
      <div className="flex gap-2 pt-3 border-t border-[#F0EEFF]">
        <div className="flex-1 h-8 bg-[#F0EEFF] rounded-lg"/>
        <div className="w-16 h-8 bg-[#F0EEFF] rounded-lg"/>
      </div>
    </div>
  );
}
