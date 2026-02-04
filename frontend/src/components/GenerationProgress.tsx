import React from 'react';

interface GenerationProgressProps {
  progress: {
    progress: number;
    message: string;
  } | null;
}

interface GenerationProgressProps {
  progress: {
    progress: number;
    message: string;
  } | null;
  title?: string;
  color?: string;
}

export default function GenerationProgress({ progress, title = "Generating Predictions", color = "blue" }: GenerationProgressProps) {
  if (!progress) return null;

  const colorClasses: { [key: string]: string } = {
    blue: "border-blue-500 text-blue-600 bg-blue-600",
    orange: "border-orange-500 text-orange-600 bg-orange-600",
  };

  const borderColor = colorClasses[color]?.split(" ")[0] || "border-blue-500";
  const textColor = colorClasses[color]?.split(" ")[1] || "text-blue-600";
  const bgColor = colorClasses[color]?.split(" ")[2] || "bg-blue-600";

  return (
    <div className={`fixed top-4 right-4 bg-white rounded-lg shadow-lg p-4 border-2 ${borderColor} z-50 min-w-[300px] max-w-[400px]`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-gray-900">{title}</h3>
        <span className={`text-sm font-semibold ${textColor}`}>{progress.progress}%</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
        <div
          className={`${bgColor} h-2.5 rounded-full transition-all duration-300`}
          style={{ width: `${progress.progress}%` }}
        />
      </div>
      <p className="text-sm text-gray-600">{progress.message}</p>
    </div>
  );
}





