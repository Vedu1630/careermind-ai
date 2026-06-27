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
    <div className="bg-white border border-[#E8E4FF] rounded-2xl p-5 animate-pulse">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-[#F0EEFF]"/>
        <div className="flex-1">
          <div className="h-4 bg-[#F0EEFF] rounded w-2/3 mb-1.5"/>
          <div className="h-3 bg-[#F0EEFF] rounded w-1/2"/>
        </div>
        <div className="w-14 h-14 rounded-full bg-[#F0EEFF]"/>
      </div>
      <div className="flex gap-2 mb-3">
        {[1,2,3].map(i => <div key={i} className="h-5 w-16 bg-[#F0EEFF] rounded-full"/>)}
      </div>
      <div className="h-8 bg-[#F0EEFF] rounded-xl"/>
    </div>
  );
}
