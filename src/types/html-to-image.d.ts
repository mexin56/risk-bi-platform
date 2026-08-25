/** html-to-image 1.11.x 未随包发布根类型声明(es/ 下仅有零散 d.ts), 此处补最小声明 */
declare module 'html-to-image' {
  export interface Options {
    filter?: (domNode: HTMLElement) => boolean;
    backgroundColor?: string;
    width?: number;
    height?: number;
    style?: Partial<CSSStyleDeclaration>;
    cacheBust?: boolean;
    imagePlaceholder?: string;
    pixelRatio?: number;
    quality?: number;
    skipFonts?: boolean;
    fontEmbedCSS?: string;
    includeQueryParams?: boolean;
  }

  export function toPng(node: HTMLElement, options?: Options): Promise<string>;
  export function toJpeg(node: HTMLElement, options?: Options): Promise<string>;
  export function toSvg(node: HTMLElement, options?: Options): Promise<string>;
  export function toBlob(node: HTMLElement, options?: Options): Promise<Blob | null>;
  export function toCanvas(node: HTMLElement, options?: Options): Promise<HTMLCanvasElement>;
  export function toPixelData(node: HTMLElement, options?: Options): Promise<Uint8ClampedArray>;
}
