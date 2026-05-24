"use client";

import { useEffect, useRef } from "react";
import createGlobe from "cobe";

export default function Globe() {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        let phi = 0;
        let width = 0;

        const onResize = () => {
            if (canvasRef.current) {
                width = canvasRef.current.offsetWidth;
            }
        };
        window.addEventListener("resize", onResize);
        onResize();

        const globe = createGlobe(canvasRef.current!, {
            devicePixelRatio: 2,
            width: width * 2,
            height: width * 2,
            phi: 0,
            theta: 0.3,
            dark: 1,
            diffuse: 6,
            mapSamples: 20000,
            mapBrightness: 6,
            baseColor: [0.3, 0.3, 0.6],
            markerColor: [0.8, 0.85, 1],
            glowColor: [0.2, 0.3, 0.7],
            markers: [],
            onRender: (state) => {
                state.phi = phi;
                phi += 0.003;
                state.width = width * 2;
                state.height = width * 2;
            },
        });

        return () => {
            globe.destroy();
            window.removeEventListener("resize", onResize);
        };
    }, []);

    return (
        <div className="w-full h-full flex items-center justify-center">
            <canvas
                ref={canvasRef}
                style={{
                    width: "100%",
                    maxWidth: "680px",
                    aspectRatio: "1",
                }}
            />
        </div>
    );
}
