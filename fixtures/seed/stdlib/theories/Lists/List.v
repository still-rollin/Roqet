(** * Lists. A small demo slice of the Rocq standard library list theory. *)

(** Concatenation of lists is associative. *)
Lemma app_assoc : forall (A : Type) (l m n : list A),
  l ++ (m ++ n) = (l ++ m) ++ n.
Proof. Admitted.

(** The empty list is a right identity for concatenation. *)
Lemma app_nil_r : forall (A : Type) (l : list A), l ++ nil = l.
Proof. Admitted.

(** Mapping the identity function over a list yields the same list. *)
Lemma map_id : forall (A : Type) (l : list A), map (fun x => x) l = l.
Proof. Admitted.

(** [map] commutes with concatenation. *)
Lemma map_app : forall (A B : Type) (f : A -> B) (l m : list A),
  map f (l ++ m) = map f l ++ map f m.
Proof. Admitted.

(** Reversing a list twice yields the original list. *)
Lemma rev_involutive : forall (A : Type) (l : list A), rev (rev l) = l.
Proof. Admitted.

(** The length of a concatenation is the sum of the lengths. *)
Lemma app_length : forall (A : Type) (l m : list A),
  length (l ++ m) = length l + length m.
Proof. Admitted.

(** Structural induction principle for lists. *)
Definition list_ind : forall (A : Type) (P : list A -> Prop),
  P nil -> (forall a l, P l -> P (cons a l)) -> forall l, P l.
Proof. Admitted.
