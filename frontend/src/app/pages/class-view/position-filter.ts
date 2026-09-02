import { Component, computed, effect, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TreeNode } from 'primeng/api';
import { TreeSelectModule } from 'primeng/treeselect';

import { PITCHER_POSITIONS, POSITION_ORDER } from '../../core/ranked-columns';

/**
 * Position filter as a two-level checkbox tree: **Pitchers** / **Batters**
 * parents whose children are the individual positions present in the class.
 * Selecting a parent selects its whole group; emits the flat list of leaf
 * positions. Clearable from the field and the adjacent button.
 */
@Component({
  selector: 'app-position-filter',
  imports: [FormsModule, TreeSelectModule],
  template: `
    <p-treeselect
      [options]="tree()"
      [ngModel]="selected()"
      (ngModelChange)="onSelectionChange($event)"
      selectionMode="checkbox"
      display="chip"
      [metaKeySelection]="false"
      [filter]="true"
      [showClear]="true"
      placeholder="All positions"
      appendTo="body"
      [style]="{ minWidth: '15rem' }"
    />
    @if (value().length) {
      <button type="button" class="clear-btn" (click)="clear()">Clear</button>
    }
  `,
  styles: [
    `
      :host { display: inline-flex; align-items: center; gap: 6px; }
      .clear-btn {
        border: none;
        background: none;
        color: var(--text-dim);
        cursor: pointer;
        font-size: 12px;
        text-decoration: underline;
      }
      .clear-btn:hover { color: var(--accent); }
    `,
  ],
})
export class PositionFilterComponent {
  readonly positions = input.required<string[]>();
  readonly value = input<string[]>([]);
  readonly valueChange = output<string[]>();

  protected readonly selected = signal<TreeNode[]>([]);

  protected readonly tree = computed<TreeNode[]>(() => {
    const present = new Set(this.positions());
    const leaf = (p: string): TreeNode => ({ key: p, label: p, data: p, leaf: true });
    const pitchers = PITCHER_POSITIONS.filter((p) => present.has(p));
    const batters = POSITION_ORDER.filter(
      (p) => present.has(p) && !PITCHER_POSITIONS.includes(p),
    );
    const extra = [...present].filter((p) => !POSITION_ORDER.includes(p)).sort();
    const groups: TreeNode[] = [];
    if (pitchers.length) {
      groups.push({ key: 'pitchers', label: 'Pitchers', selectable: true, children: pitchers.map(leaf) });
    }
    if (batters.length || extra.length) {
      groups.push({
        key: 'batters',
        label: 'Batters',
        selectable: true,
        children: [...batters, ...extra].map(leaf),
      });
    }
    return groups;
  });

  constructor() {
    // Keep the tree's checkbox state in sync with the parent's string list
    // (the parent resets it to [] on class switch).
    effect(() => {
      const wanted = new Set(this.value());
      const nodes: TreeNode[] = [];
      for (const group of this.tree()) {
        const kids = group.children ?? [];
        const picked = kids.filter((c) => wanted.has(c.data as string));
        if (!picked.length) {
          group.partialSelected = false;
          continue;
        }
        nodes.push(...picked);
        if (picked.length === kids.length) {
          group.partialSelected = false;
          nodes.push(group);
        } else {
          group.partialSelected = true;
        }
      }
      this.selected.set(nodes);
    });
  }

  protected onSelectionChange(nodes: TreeNode[] | TreeNode | null): void {
    const arr = Array.isArray(nodes) ? nodes : nodes ? [nodes] : [];
    const leaves = new Set<string>();
    for (const n of arr) {
      if (n.children?.length) {
        n.children.forEach((c) => c.data && leaves.add(c.data as string));
      } else if (n.data) {
        leaves.add(n.data as string);
      }
    }
    this.selected.set(arr);
    this.valueChange.emit([...leaves]);
  }

  protected clear(): void {
    this.selected.set([]);
    this.valueChange.emit([]);
  }
}
