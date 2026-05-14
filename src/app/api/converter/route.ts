import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const file = searchParams.get('file');

  const validFiles = [
    'kirin.geo.json',
    'kirin.animation.json',
    'kirin_bone_mapping.json',
    'KirinGeoModel.java',
  ];

  if (!file || !validFiles.includes(file)) {
    return NextResponse.json({ error: 'Invalid file' }, { status: 400 });
  }

  try {
    const filePath = path.join(process.cwd(), 'converter', 'output', file);
    const content = fs.readFileSync(filePath, 'utf-8');

    const contentTypes: Record<string, string> = {
      'kirin.geo.json': 'application/json',
      'kirin.animation.json': 'application/json',
      'kirin_bone_mapping.json': 'application/json',
      'KirinGeoModel.java': 'text/plain',
    };

    return new NextResponse(content, {
      headers: {
        'Content-Type': contentTypes[file] || 'application/octet-stream',
        'Cache-Control': 'no-cache',
      },
    });
  } catch {
    return NextResponse.json({ error: 'File not found' }, { status: 404 });
  }
}
