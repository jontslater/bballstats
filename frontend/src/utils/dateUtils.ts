/**
 * Date utility functions to handle timezone issues.
 * 
 * When parsing date strings in YYYY-MM-DD format, using new Date() directly
 * can cause timezone issues (e.g., "2025-12-30" becomes Dec 29 in CST).
 * These utilities parse dates without timezone conversion.
 */
import { format } from 'date-fns';

/**
 * Parse a date string (YYYY-MM-DD) without timezone conversion.
 * Returns a Date object at local midnight.
 */
export function parseDateString(dateString: string): Date {
  const dateParts = dateString.split('-');
  if (dateParts.length !== 3) {
    // Fallback to standard parsing if format is unexpected
    return new Date(dateString);
  }
  const year = parseInt(dateParts[0], 10);
  const month = parseInt(dateParts[1], 10) - 1; // Month is 0-indexed
  const day = parseInt(dateParts[2], 10);
  return new Date(year, month, day);
}

/**
 * Format a date string (YYYY-MM-DD) using date-fns format function.
 * This avoids timezone issues when displaying dates.
 */
export function formatDateString(dateString: string, formatStr: string): string {
  const date = parseDateString(dateString);
  return format(date, formatStr);
}

/**
 * Format a Date object into a 'MMM d, yyyy' string.
 * @param date A Date object.
 * @returns Formatted date string.
 */
export function formatDateDisplay(date: Date): string {
  return format(date, 'MMM d, yyyy');
}

