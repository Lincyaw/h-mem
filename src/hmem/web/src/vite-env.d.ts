/// <reference types="vite/client" />

declare module "react-cytoscapejs" {
  import type { Core, ElementDefinition } from "cytoscape";
  import type { ComponentType } from "react";

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  type CyStylesheet = Array<{ selector: string; style: Record<string, any> }>;

  interface CytoscapeComponentProps {
    elements: ElementDefinition[];
    stylesheet?: CyStylesheet;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    layout?: Record<string, any>;
    cy?: (cy: Core) => void;
    style?: React.CSSProperties;
    className?: string;
  }

  const CytoscapeComponent: ComponentType<CytoscapeComponentProps>;
  export default CytoscapeComponent;
}
