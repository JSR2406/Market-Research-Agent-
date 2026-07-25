"use client";
import React, { useEffect, useState, useId } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  securityLevel: "loose",
});

export default function Mermaid({ chart }: { chart: string }) {
  const [svgData, setSvgData] = useState<string>("");
  const id = "mermaid-" + useId().replace(/:/g, "");

  useEffect(() => {
    let isMounted = true;
    
    const renderChart = async () => {
      try {
        const { svg } = await mermaid.render(id, chart);
        if (isMounted) setSvgData(svg);
      } catch (error) {
        console.error("Mermaid parsing failed", error);
        if (isMounted) setSvgData("<div style='color:var(--error); padding:1rem; border:1px solid var(--error)'>Failed to render chart</div>");
      }
    };
    
    if (chart) {
      renderChart();
    }
    
    return () => {
      isMounted = false;
    };
  }, [chart, id]);

  return (
    <div 
      className="mermaid-wrapper" 
      style={{ display: "flex", justifyContent: "center", margin: "2rem 0" }}
      dangerouslySetInnerHTML={{ __html: svgData || "<div style='padding: 2rem'>Loading chart...</div>" }} 
    />
  );
}
