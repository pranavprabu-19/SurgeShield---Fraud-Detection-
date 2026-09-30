"use client";
import { useEffect, useRef } from "react";

export default function CyberBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    
    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    const columns = Math.floor(width / 20);
    const drops = [];
    for (let i = 0; i < columns; i++) drops[i] = 1;

    let frameId;
    let lastDraw = 0;
    
    function draw(timestamp) {
      if (timestamp - lastDraw > 50) { // Limit framerate for matrix effect
        ctx.fillStyle = "rgba(11, 18, 32, 0.1)"; 
        ctx.fillRect(0, 0, width, height);

        ctx.fillStyle = "#3ee0c5"; // SurgeShield Mint
        ctx.font = "14px monospace";

        for (let i = 0; i < drops.length; i++) {
          const text = Math.random() > 0.5 ? "1" : "0";
          ctx.fillText(text, i * 20, drops[i] * 20);

          if (drops[i] * 20 > height && Math.random() > 0.95) {
            drops[i] = 0;
          }
          drops[i]++;
        }
        lastDraw = timestamp;
      }
      frameId = requestAnimationFrame(draw);
    }
    
    frameId = requestAnimationFrame(draw);

    function onResize() {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    }
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return (
    <canvas 
      ref={canvasRef} 
      className="fixed inset-0 pointer-events-none z-0 opacity-[0.08]" 
      style={{ display: "block" }} 
    />
  );
}
