import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Guardly - Hallucination Detection Chat',
  description: 'Chat interface with real-time hallucination detection using Guardly',
  charset: 'utf-8',
  viewport: 'width=device-width, initial-scale=1',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased bg-gray-50">{children}</body>
    </html>
  );
}
