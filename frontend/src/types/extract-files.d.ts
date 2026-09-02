declare module 'extract-files/extractFiles.mjs' {
  const extractFiles: (
    value: unknown,
    isExtractable: (value: unknown) => boolean,
    path?: string,
  ) => { clone: unknown; files: Map<unknown, string[]> };
  export default extractFiles;
}

declare module 'extract-files/isExtractableFile.mjs' {
  const isExtractableFile: (value: unknown) => boolean;
  export default isExtractableFile;
}
