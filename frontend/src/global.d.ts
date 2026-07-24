declare const marked: {
  parse(text: string, options?: { breaks?: boolean }): string;
};

declare const DOMPurify: {
  sanitize(html: string, options?: { ADD_ATTR?: string[] }): string;
};
