import React from 'react';

interface GenerationProgressProps {
  progress: {
    progress: number;
    message: string;
  } | null;
}

export default function GenerationProgress({ progress }: GenerationProgressProps) {
  if (!progress) return null;

  return (
    <div className="fixed top-4 right-4 bg-white rounded-lg shadow-lg p-4 border-2 border-blue-500 z-50 min-w-[300px] max-w-[400px]">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-gray-900">Generating Predictions</h3>
        <span className="text-sm font-semibold text-blue-600">{progress.progress}%</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
        <div
          className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
          style={{ width: `${progress.progress}%` }}
        />
      </div>
      <p className="text-sm text-gray-600">{progress.message}</p>
    </div>
  );
}


