(** * Path groupoids. A small demo slice of the HoTT library. *)

(** Path induction: to prove a property of all paths it suffices to prove it for [idpath]. *)
Definition paths_ind : forall (A : Type) (a : A) (P : forall b, a = b -> Type),
  P a idpath -> forall b (p : a = b), P b p.
Proof. Admitted.

(** Concatenation of paths is associative. *)
Lemma concat_p_pp : forall (A : Type) (x y z w : A) (p : x = y) (q : y = z) (r : z = w),
  p @ (q @ r) = (p @ q) @ r.
Proof. Admitted.

(** The inverse of a path is a left inverse under concatenation. *)
Lemma concat_Vp : forall (A : Type) (x y : A) (p : x = y), p^ @ p = idpath.
Proof. Admitted.

(** Transport along the concatenation of two paths. *)
Lemma transport_pp : forall (A : Type) (P : A -> Type) (x y z : A)
  (p : x = y) (q : y = z) (u : P x),
  transport P (p @ q) u = transport P q (transport P p u).
Proof. Admitted.
