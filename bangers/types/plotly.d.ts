declare module 'plotly.js-dist-min' {
  const Plotly: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    restyle: (graphDiv: any, update: any, traces?: number[]) => Promise<void>;
    // Add other methods as needed
  };
  export default Plotly;
}
