import { Component, effect, input, output, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import {
  CdkDrag,
  CdkDragDrop,
  CdkDropList,
  moveItemInArray,
} from '@angular/cdk/drag-drop';

export interface ReorderRow {
  id: string;
  name: string;
  position: string;
  age: number | null;
  modelScore: number | null;
  drafted: boolean;
}

/** Drag-to-reorder list for setting a class's custom ranking order. */
@Component({
  selector: 'app-reorder-panel',
  imports: [DecimalPipe, CdkDropList, CdkDrag],
  templateUrl: './reorder-panel.html',
  styleUrl: './reorder-panel.scss',
})
export class ReorderPanelComponent {
  readonly players = input.required<ReorderRow[]>();
  readonly busy = input(false);

  readonly save = output<string[]>();
  readonly cancel = output<void>();
  readonly revert = output<void>();

  protected readonly list = signal<ReorderRow[]>([]);

  constructor() {
    effect(() => {
      const src = this.players();
      this.list.set([...src]);
    });
  }

  protected drop(ev: CdkDragDrop<ReorderRow[]>): void {
    const list = [...this.list()];
    moveItemInArray(list, ev.previousIndex, ev.currentIndex);
    this.list.set(list);
  }

  protected onSave(): void {
    this.save.emit(this.list().map((p) => p.id));
  }
}
