import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { Maximize2, Minus, Plus } from "lucide-react";
import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  WORK_PROJECT_ASSET_TYPE,
  WORK_PROJECT_ASSET_TYPES,
  WORK_PROJECT_GRAPH_EDGE_CATEGORIES,
  workProjectEdgeCategory,
  type WorkProjectGraphEdgeCategory,
} from "../../shared/api/contract";
import type { WorkProjectAsset, WorkProjectAssetType, WorkProjectGraphEdge } from "../../shared/api/types";
import {
  WORK_PROJECT_ASSET_ORIGIN_LABEL,
  WORK_PROJECT_ASSET_TYPE_LABEL,
  WORK_PROJECT_GRAPH_EDGE_CATEGORY_LABEL,
  WORK_PROJECT_GRAPH_EDGE_TYPE_LABEL,
} from "../../shared/lib/labels";
import { filledDetailItems, type DetailItem, type FilledDetailItem } from "./workProjectDetails";
import { formatWorkProjectAsset } from "./workProjectView";

cytoscape.use(fcose);

const ASSET_TYPE_COLOR: Record<WorkProjectAssetType, string> = {
  [WORK_PROJECT_ASSET_TYPE.SERVICE]: "#65a9ff",
  [WORK_PROJECT_ASSET_TYPE.DOMAIN]: "#42d6c5",
  [WORK_PROJECT_ASSET_TYPE.NETWORK]: "#a78bfa",
  [WORK_PROJECT_ASSET_TYPE.BINARY]: "#f7bd54",
};

const ASSET_TYPE_BORDER: Record<WorkProjectAssetType, string> = {
  [WORK_PROJECT_ASSET_TYPE.SERVICE]: "#d7eaff",
  [WORK_PROJECT_ASSET_TYPE.DOMAIN]: "#d6fff9",
  [WORK_PROJECT_ASSET_TYPE.NETWORK]: "#eee7ff",
  [WORK_PROJECT_ASSET_TYPE.BINARY]: "#fff0c7",
};

const EDGE_CATEGORY_COLOR: Record<WorkProjectGraphEdgeCategory, string> = {
  structural: "#8ea5bf",
  offensive: "#ff7d8a",
};

const FIT_PADDING = 84;
const MIN_ZOOM = 0.06;
const MAX_ZOOM = 4;
const WHEEL_SENSITIVITY = 1.6;
const TOOLTIP_OFFSET = 14;
const TOOLTIP_MARGIN = 10;
const NODE_SIZE = 12;
const CONTROL_ZOOM_FACTOR = 1.45;

type HoverTarget =
  | { kind: "node"; asset: WorkProjectAsset }
  | { kind: "edge"; edge: WorkProjectGraphEdge };
type HoverState = { target: HoverTarget; left: number; top: number; containerWidth: number; containerHeight: number };
type TooltipRows = { title: string; items: FilledDetailItem[] };

type FcoseLayoutOptions = cytoscape.BaseLayoutOptions & {
  name: "fcose";
  quality: "draft" | "default" | "proof";
  randomize: boolean;
  animate: boolean;
  fit: boolean;
  padding: number;
  nodeDimensionsIncludeLabels: boolean;
  uniformNodeDimensions: boolean;
  packComponents: boolean;
  nodeSeparation: number;
  nodeRepulsion: number;
  idealEdgeLength: number;
  edgeElasticity: number;
  gravity: number;
  gravityRange: number;
  numIter: number;
};

export function ProjectGraphCanvas({ assets, edges }: { assets: WorkProjectAsset[]; edges: WorkProjectGraphEdge[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const layoutRef = useRef<cytoscape.Layouts | null>(null);

  const assetById = useMemo(() => new Map(assets.map((asset) => [asset.id, asset])), [assets]);
  const visibleEdges = useMemo(
    () => edges.filter((edge) => assetById.has(edge.source_asset_id) && assetById.has(edge.target_asset_id)),
    [edges, assetById],
  );
  const edgeById = useMemo(() => new Map(visibleEdges.map((edge) => [edge.id, edge])), [visibleEdges]);
  const elements = useMemo(() => graphElements(assets, visibleEdges), [assets, visibleEdges]);
  const [hover, setHover] = useState<HoverState | null>(null);

  const clearGraphHover = useCallback(() => {
    const cy = cyRef.current;
    cy?.elements(".is-hovered").removeClass("is-hovered");
    setHover(null);
  }, []);

  const showHover = useCallback((event: cytoscape.EventObject, target: HoverTarget) => {
    const rect = containerRef.current?.getBoundingClientRect();
    const rendered = event.renderedPosition;
    event.cy.elements(".is-hovered").removeClass("is-hovered");
    event.target.addClass("is-hovered");
    setHover({
      target,
      left: rendered.x,
      top: rendered.y,
      containerWidth: rect?.width ?? 0,
      containerHeight: rect?.height ?? 0,
    });
  }, []);

  useEffect(() => {
    if (!graphRef.current || cyRef.current) return;

    const cy = createGraph(graphRef.current);
    cyRef.current = cy;

    const resizeObserver = new ResizeObserver(() => {
      cy.resize();
      cy.fit(undefined, FIT_PADDING);
    });
    resizeObserver.observe(graphRef.current);

    return () => {
      resizeObserver.disconnect();
      layoutRef.current?.stop();
      layoutRef.current = null;
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    const onNodeHover = hoverHandler(assetById, "assetId", (asset) => ({ kind: "node", asset }), showHover);
    const onEdgeHover = hoverHandler(edgeById, "edgeId", (edge) => ({ kind: "edge", edge }), showHover);

    cy.on("mouseover mousemove", "node", onNodeHover);
    cy.on("mouseover mousemove", "edge", onEdgeHover);
    cy.on("mouseout", "node, edge", clearGraphHover);
    cy.on("dragpan zoom resize", clearGraphHover);

    return () => {
      cy.off("mouseover mousemove", "node", onNodeHover);
      cy.off("mouseover mousemove", "edge", onEdgeHover);
      cy.off("mouseout", "node, edge", clearGraphHover);
      cy.off("dragpan zoom resize", clearGraphHover);
    };
  }, [assetById, clearGraphHover, edgeById, showHover]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    clearGraphHover();
    layoutRef.current?.stop();
    layoutRef.current = null;
    cy.elements().remove();

    if (!assets.length) return;

    cy.add(elements);
    const layout = runGraphLayout(cy, assets.length, visibleEdges.length, () => {
      layoutRef.current = null;
    });

    layoutRef.current = layout;
  }, [assets.length, clearGraphHover, elements, visibleEdges.length]);

  const zoomFromCenter = (factor: number) => {
    const cy = cyRef.current;
    const graph = graphRef.current;
    if (!cy || !graph) return;
    const current = cy.zoom();
    const next = clamp(current * factor, MIN_ZOOM, MAX_ZOOM);
    cy.zoom({
      level: next,
      renderedPosition: { x: graph.clientWidth / 2, y: graph.clientHeight / 2 },
    });
  };

  const resetView = () => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.resize();
    cy.fit(undefined, FIT_PADDING);
  };

  return (
    <div className="project-graph" ref={containerRef}>
      <div ref={graphRef} className="project-graph-canvas" role="img" aria-label="Work project relationship graph" />

      <GraphLegend />

      <div className="project-graph-controls">
        <button type="button" aria-label="Zoom in" onClick={() => zoomFromCenter(CONTROL_ZOOM_FACTOR)}>
          <Plus size={15} />
        </button>
        <button type="button" aria-label="Zoom out" onClick={() => zoomFromCenter(1 / CONTROL_ZOOM_FACTOR)}>
          <Minus size={15} />
        </button>
        <button type="button" aria-label="Reset view" onClick={resetView}>
          <Maximize2 size={14} />
        </button>
      </div>

      {hover ? <GraphTooltip hover={hover} assetById={assetById} /> : null}
    </div>
  );
}

function hoverHandler<T>(
  items: Map<number, T>,
  dataKey: string,
  target: (item: T) => HoverTarget,
  showHover: (event: cytoscape.EventObject, target: HoverTarget) => void,
): (event: cytoscape.EventObject) => void {
  return (event) => {
    const item = items.get(event.target.data(dataKey));
    if (item) showHover(event, target(item));
  };
}

function createGraph(container: HTMLDivElement): cytoscape.Core {
  return cytoscape({
    container,
    elements: [],
    minZoom: MIN_ZOOM,
    maxZoom: MAX_ZOOM,
    wheelSensitivity: WHEEL_SENSITIVITY,
    boxSelectionEnabled: false,
    autoungrabify: false,
    hideLabelsOnViewport: true,
    style: graphStyles(),
  });
}

function runGraphLayout(
  cy: cytoscape.Core,
  assetCount: number,
  edgeCount: number,
  onStop: () => void,
): cytoscape.Layouts {
  const layoutOptions = graphLayoutOptions(assetCount, edgeCount, () => {
    cy.fit(undefined, FIT_PADDING);
    onStop();
  });
  const layout = cy.layout(layoutOptions);
  layout.run();
  return layout;
}

function graphLayoutOptions(assetCount: number, edgeCount: number, stop: () => void): FcoseLayoutOptions {
  const dense = edgeCount / Math.max(assetCount, 1);
  return {
    name: "fcose",
    quality: assetCount > 220 ? "default" : "proof",
    randomize: true,
    animate: false,
    fit: true,
    padding: FIT_PADDING,
    nodeDimensionsIncludeLabels: true,
    uniformNodeDimensions: false,
    packComponents: false,
    nodeSeparation: clamp(128 + Math.sqrt(edgeCount) * 3 + dense * 10, 128, 210),
    nodeRepulsion: nodeRepulsionForGraph(assetCount, dense),
    idealEdgeLength: idealEdgeLengthForGraph(edgeCount, dense),
    edgeElasticity: 0.18,
    gravity: 0.05,
    gravityRange: 6.5,
    numIter: assetCount > 220 ? 2200 : 3600,
    stop,
  };
}

function graphElements(
  assets: WorkProjectAsset[],
  edges: WorkProjectGraphEdge[],
): cytoscape.ElementDefinition[] {
  return [...assets.map(nodeElement), ...edges.map(edgeElement)];
}

function nodeElement(asset: WorkProjectAsset): cytoscape.ElementDefinition {
  return {
    group: "nodes",
    data: {
      id: assetNodeId(asset.id),
      assetId: asset.id,
      label: truncate(formatWorkProjectAsset(asset), 28),
      accent: ASSET_TYPE_COLOR[asset.type],
      border: ASSET_TYPE_BORDER[asset.type],
    },
  };
}

function edgeElement(edge: WorkProjectGraphEdge): cytoscape.ElementDefinition {
  const category = workProjectEdgeCategory(edge.type);
  return {
    group: "edges",
    data: {
      id: edgeElementId(edge.id),
      edgeId: edge.id,
      source: assetNodeId(edge.source_asset_id),
      target: assetNodeId(edge.target_asset_id),
      label: WORK_PROJECT_GRAPH_EDGE_TYPE_LABEL[edge.type],
      category,
      color: EDGE_CATEGORY_COLOR[category],
    },
  };
}

function graphStyles(): cytoscape.StylesheetJson {
  return [
    {
      selector: "core",
      style: {
        "selection-box-color": "#7ddbd3",
        "selection-box-border-color": "#d6fff9",
        "selection-box-opacity": 0.16,
        "active-bg-color": "#7ddbd3",
        "active-bg-size": 18,
        "active-bg-opacity": 0.12,
        "selection-box-border-width": 1,
        "outside-texture-bg-color": "#08111c",
        "outside-texture-bg-opacity": 0.9,
      },
    },
    {
      selector: "node",
      style: {
        width: NODE_SIZE,
        height: NODE_SIZE,
        shape: "ellipse",
        "background-color": "data(accent)",
        "background-opacity": 0.94,
        "border-color": "data(border)",
        "border-width": 1,
        content: "data(label)",
        "font-size": 8.5,
        "font-weight": 600,
        "line-height": 1.2,
        "text-wrap": "wrap",
        "text-max-width": "96px",
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 6,
        "min-zoomed-font-size": 7.5,
        "color": "#c7d2df",
        "text-outline-color": "#08111c",
        "text-outline-width": 2.5,
        "overlay-opacity": 0,
        "underlay-color": "data(accent)",
        "underlay-opacity": 0,
        "underlay-padding": 3,
        "transition-property": "background-opacity, border-width, underlay-opacity",
        "transition-duration": 0.12,
      },
    },
    {
      selector: "node:selected, node.is-hovered",
      style: {
        "background-opacity": 1,
        "border-width": 1.75,
        "underlay-opacity": 0.22,
      },
    },
    {
      selector: "edge",
      style: {
        width: 1.35,
        "line-color": "data(color)",
        "target-arrow-color": "data(color)",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.8,
        "curve-style": "bezier",
        "control-point-step-size": 46,
        "line-cap": "round",
        "source-distance-from-node": 1,
        "target-distance-from-node": 2,
        "opacity": 0.76,
        content: "",
        "font-size": 10,
        "font-weight": 600,
        "text-rotation": "autorotate",
        "text-margin-y": -10,
        "min-zoomed-font-size": 8,
        "color": "#aebdca",
        "text-outline-color": "#08111c",
        "text-outline-width": 3,
        "overlay-opacity": 0,
        "transition-property": "width, opacity",
        "transition-duration": 0.12,
      },
    },
    {
      selector: 'edge[category = "offensive"]',
      style: {
        width: 1.85,
        "line-style": "dashed",
        "opacity": 0.9,
      },
    },
    {
      selector: "edge:selected, edge.is-hovered",
      style: {
        width: 2.7,
        "opacity": 1,
        content: "data(label)",
        "z-index": 999,
      },
    },
  ];
}

function GraphLegend() {
  return (
    <div className="project-graph-legend">
      <div className="project-graph-legend-group">
        <span className="project-graph-legend-title">Nodes</span>
        {WORK_PROJECT_ASSET_TYPES.map((type) => (
          <span key={type} className="project-graph-legend-item">
            <i className="project-graph-legend-dot" style={graphColorStyle(ASSET_TYPE_COLOR[type])} />
            {WORK_PROJECT_ASSET_TYPE_LABEL[type]}
          </span>
        ))}
      </div>
      <div className="project-graph-legend-group">
        <span className="project-graph-legend-title">Edges</span>
        {WORK_PROJECT_GRAPH_EDGE_CATEGORIES.map((category) => (
          <span key={category} className="project-graph-legend-item">
            <i
              className={`project-graph-legend-line${category === "offensive" ? " project-graph-legend-line-offensive" : ""}`}
              style={graphColorStyle(EDGE_CATEGORY_COLOR[category])}
            />
            {WORK_PROJECT_GRAPH_EDGE_CATEGORY_LABEL[category]}
          </span>
        ))}
      </div>
    </div>
  );
}

type GraphColorStyle = CSSProperties & { "--graph-color": string };

function graphColorStyle(color: string): GraphColorStyle {
  return { "--graph-color": color };
}

function GraphTooltip({ hover, assetById }: { hover: HoverState; assetById: Map<number, WorkProjectAsset> }) {
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const rows = useMemo(
    () => hover.target.kind === "node"
      ? nodeRows(hover.target.asset)
      : edgeRows(hover.target.edge, assetById),
    [assetById, hover.target],
  );

  useLayoutEffect(() => {
    const element = tooltipRef.current;
    if (!element) return;
    const updateSize = () => {
      const next = { width: element.offsetWidth, height: element.offsetHeight };
      setSize((current) => (
        current.width === next.width && current.height === next.height ? current : next
      ));
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(element);
    return () => observer.disconnect();
  }, [rows]);

  const style = tooltipStyle(hover, size);

  return (
    <div ref={tooltipRef} className="project-graph-tooltip" style={style}>
      <strong>{rows.title}</strong>
      <dl>
        {rows.items.map(([label, value]) => (
          <Fragment key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </Fragment>
        ))}
      </dl>
    </div>
  );
}

function tooltipStyle(hover: HoverState, size: { width: number; height: number }): { left: number; top: number } {
  const width = size.width || 260;
  const height = size.height || 120;
  const maxLeft = Math.max(TOOLTIP_MARGIN, hover.containerWidth - width - TOOLTIP_MARGIN);
  const maxTop = Math.max(TOOLTIP_MARGIN, hover.containerHeight - height - TOOLTIP_MARGIN);
  const left = hover.left + TOOLTIP_OFFSET + width > hover.containerWidth - TOOLTIP_MARGIN
    ? hover.left - width - TOOLTIP_OFFSET
    : hover.left + TOOLTIP_OFFSET;
  const top = hover.top + TOOLTIP_OFFSET + height > hover.containerHeight - TOOLTIP_MARGIN
    ? hover.top - height - TOOLTIP_OFFSET
    : hover.top + TOOLTIP_OFFSET;
  return {
    left: clamp(left, TOOLTIP_MARGIN, maxLeft),
    top: clamp(top, TOOLTIP_MARGIN, maxTop),
  };
}

function nodeRows(asset: WorkProjectAsset): TooltipRows {
  const items: DetailItem[] = [
    ["Type", WORK_PROJECT_ASSET_TYPE_LABEL[asset.type]],
    ["Origin", WORK_PROJECT_ASSET_ORIGIN_LABEL[asset.origin]],
    asset.type === WORK_PROJECT_ASSET_TYPE.BINARY ? ["Path", asset.path] : ["Host", asset.host],
    ["Port", asset.port ? String(asset.port) : undefined],
    ["Banner", asset.extra?.banner],
  ];
  return { title: formatWorkProjectAsset(asset), items: filledDetailItems(items) };
}

function edgeRows(edge: WorkProjectGraphEdge, assetById: Map<number, WorkProjectAsset>): TooltipRows {
  const source = assetById.get(edge.source_asset_id);
  const target = assetById.get(edge.target_asset_id);
  const items: DetailItem[] = [
    ["Category", WORK_PROJECT_GRAPH_EDGE_CATEGORY_LABEL[workProjectEdgeCategory(edge.type)]],
    ["From", source ? formatWorkProjectAsset(source) : `#${edge.source_asset_id}`],
    ["To", target ? formatWorkProjectAsset(target) : `#${edge.target_asset_id}`],
    ["Label", edge.label],
  ];
  return { title: WORK_PROJECT_GRAPH_EDGE_TYPE_LABEL[edge.type], items: filledDetailItems(items) };
}

function assetNodeId(id: number): string {
  return `asset:${id}`;
}

function edgeElementId(id: number): string {
  return `edge:${id}`;
}

function nodeRepulsionForGraph(nodeCount: number, density: number): number {
  return clamp(12000 + Math.sqrt(nodeCount) * 1800 + density * 1800, 12000, 42000);
}

function idealEdgeLengthForGraph(edgeCount: number, density: number): number {
  return clamp(150 + Math.sqrt(edgeCount) * 10 + density * 18, 150, 340);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max - 1)}...`;
}
