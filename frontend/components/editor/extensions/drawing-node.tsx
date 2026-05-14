import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import React, { useState, useRef, useEffect } from "react";
import { MousePointer2, Square, Circle, Minus, Pencil, Eraser } from "lucide-react";

export const DrawingComponent = ({ node, updateAttributes }: any) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [tool, setTool] = useState<"pencil" | "rect" | "circle" | "line" | "eraser">("pencil");
  const [color, setColor] = useState("#ffffff");
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });
  const [canvasData, setCanvasData] = useState<string>(node.attrs.dataUrl || "");

  useEffect(() => {
    if (canvasData && canvasRef.current) {
      const ctx = canvasRef.current.getContext("2d");
      const img = new Image();
      img.onload = () => {
        if (ctx && canvasRef.current) {
          ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
          ctx.drawImage(img, 0, 0);
        }
      };
      img.src = canvasData;
    }
  }, []);

  const saveCanvas = () => {
    if (canvasRef.current) {
      const dataUrl = canvasRef.current.toDataURL();
      setCanvasData(dataUrl);
      updateAttributes({ dataUrl });
    }
  };

  const getCoordinates = (e: React.MouseEvent<HTMLCanvasElement> | MouseEvent) => {
    if (!canvasRef.current) return { x: 0, y: 0 };
    const rect = canvasRef.current.getBoundingClientRect();
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    setIsDrawing(true);
    const pos = getCoordinates(e);
    setStartPos(pos);
    
    if (tool === "pencil" || tool === "eraser") {
      const ctx = canvasRef.current?.getContext("2d");
      if (ctx) {
        ctx.beginPath();
        ctx.moveTo(pos.x, pos.y);
        ctx.strokeStyle = tool === "eraser" ? "#18181b" : color; // Match bg color for eraser
        ctx.lineWidth = tool === "eraser" ? 10 : 2;
        ctx.lineCap = "round";
      }
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing || !canvasRef.current) return;
    const pos = getCoordinates(e);
    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    if (tool === "pencil" || tool === "eraser") {
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
    } else {
      // For shapes, we need to redraw the saved state and then the current shape preview.
      // To keep it simple for this phase, we'll just draw on mouseup.
    }
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing || !canvasRef.current) return;
    setIsDrawing(false);
    const pos = getCoordinates(e);
    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    if (tool === "rect") {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(startPos.x, startPos.y, pos.x - startPos.x, pos.y - startPos.y);
    } else if (tool === "circle") {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      const radius = Math.sqrt(Math.pow(pos.x - startPos.x, 2) + Math.pow(pos.y - startPos.y, 2));
      ctx.arc(startPos.x, startPos.y, radius, 0, 2 * Math.PI);
      ctx.stroke();
    } else if (tool === "line") {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(startPos.x, startPos.y);
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
    }

    saveCanvas();
  };

  return (
    <NodeViewWrapper className="drawing-block my-4 p-2 bg-zinc-900 border border-zinc-800 rounded-lg">
      <div className="flex items-center gap-2 mb-2 p-1 bg-zinc-950 rounded select-none">
        <button onClick={() => setTool("pencil")} className={`p-1.5 rounded \${tool === "pencil" ? "bg-zinc-800 text-indigo-400" : "text-zinc-400"}`} title="Pencil">
          <Pencil className="w-4 h-4" />
        </button>
        <button onClick={() => setTool("line")} className={`p-1.5 rounded \${tool === "line" ? "bg-zinc-800 text-indigo-400" : "text-zinc-400"}`} title="Line">
          <Minus className="w-4 h-4" />
        </button>
        <button onClick={() => setTool("rect")} className={`p-1.5 rounded \${tool === "rect" ? "bg-zinc-800 text-indigo-400" : "text-zinc-400"}`} title="Rectangle">
          <Square className="w-4 h-4" />
        </button>
        <button onClick={() => setTool("circle")} className={`p-1.5 rounded \${tool === "circle" ? "bg-zinc-800 text-indigo-400" : "text-zinc-400"}`} title="Circle">
          <Circle className="w-4 h-4" />
        </button>
        <button onClick={() => setTool("eraser")} className={`p-1.5 rounded \${tool === "eraser" ? "bg-zinc-800 text-indigo-400" : "text-zinc-400"}`} title="Eraser">
          <Eraser className="w-4 h-4" />
        </button>
        <div className="w-px h-4 bg-zinc-800 mx-1" />
        <input 
          type="color" 
          value={color} 
          onChange={(e) => setColor(e.target.value)} 
          className="w-6 h-6 rounded cursor-pointer border-0 p-0"
          title="Color"
        />
        <div className="w-px h-4 bg-zinc-800 mx-1" />
        <button 
          onClick={() => {
            const ctx = canvasRef.current?.getContext("2d");
            if (ctx && canvasRef.current) {
              ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
              saveCanvas();
            }
          }}
          className="text-xs text-red-400 hover:text-red-300 ml-auto mr-2"
        >
          Clear Canvas
        </button>
      </div>
      <div className="flex justify-center bg-zinc-950 rounded border border-zinc-800 overflow-hidden">
        <canvas
          ref={canvasRef}
          width={600}
          height={300}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="cursor-crosshair bg-[#18181b]"
          style={{ width: "100%", maxWidth: "600px", height: "auto", aspectRatio: "2/1" }}
        />
      </div>
    </NodeViewWrapper>
  );
};

export const DrawingBlock = Node.create({
  name: "drawingBlock",
  group: "block",
  atom: true,

  addAttributes() {
    return {
      dataUrl: { default: "" },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="drawing-block"]',
        getAttrs: (el) => {
          const element = el as HTMLElement;
          return { dataUrl: element.getAttribute("data-url") || "" };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "drawing-block",
        "data-url": HTMLAttributes.dataUrl,
      }),
      // In print mode, render an img tag with the dataUrl
      HTMLAttributes.dataUrl ? ["img", { src: HTMLAttributes.dataUrl, style: "max-width: 100%;" }] : ["div", {}, "Empty Drawing"],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(DrawingComponent);
  },
});
