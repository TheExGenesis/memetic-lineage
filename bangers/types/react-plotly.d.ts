declare module 'react-plotly.js' {
  import { Component } from 'react';
  import Plotly from 'plotly.js-dist-min';

  interface PlotParams {
    data: Plotly.Data[];
    layout?: Partial<Plotly.Layout>;
    config?: Partial<Plotly.Config>;
    frames?: Plotly.Frame[];
    style?: React.CSSProperties;
    className?: string;
    useResizeHandler?: boolean;
    onInitialized?: (figure: Readonly<{ data: Plotly.Data[]; layout: Partial<Plotly.Layout> }>, graphDiv: HTMLElement) => void;
    onUpdate?: (figure: Readonly<{ data: Plotly.Data[]; layout: Partial<Plotly.Layout> }>, graphDiv: HTMLElement) => void;
    onPurge?: (figure: Readonly<{ data: Plotly.Data[]; layout: Partial<Plotly.Layout> }>, graphDiv: HTMLElement) => void;
    onError?: (err: Error) => void;
    onRelayout?: (event: any) => void;
    onClick?: (event: any) => void;
    onHover?: (event: any) => void;
    onUnhover?: (event: any) => void;
    onSelected?: (event: any) => void;
    onDeselect?: (event: any) => void;
    onDoubleClick?: (event: any) => void;
    onRestyle?: (event: any) => void;
    onRedraw?: () => void;
    onAnimated?: () => void;
    onAfterPlot?: () => void;
    onBeforePlot?: (event: any) => boolean;
    onLegendClick?: (event: any) => boolean;
    onLegendDoubleClick?: (event: any) => boolean;
    onSliderChange?: (event: any) => void;
    onSliderEnd?: (event: any) => void;
    onSliderStart?: (event: any) => void;
    onFramework?: (event: any) => void;
    onAnimatingFrame?: (event: any) => void;
    onTransitioning?: () => void;
    onTransitionInterrupted?: () => void;
    divId?: string;
  }

  export default class Plot extends Component<PlotParams> {}
}
